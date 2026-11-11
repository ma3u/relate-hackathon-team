"""Week-1 proof: Klarbefund FHIR Bundles -> local Relate graph -> demo queries."""
import shutil
import subprocess
from pathlib import Path

import pytest

from health_graph import fhir, store
from health_graph.queries import QUERIES

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))
GOLDEN = ROOT / "fixtures" / "fhir" / "2026-09-04-praxis-muster.json"


def q(conn, name, **params):
    return [dict(r) for r in conn.execute(QUERIES[name][1], params)]


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "health.rl"
    conn = store.connect(path)
    store.init_schema(conn)
    for b in BUNDLES:
        store.import_report(conn, fhir.parse_bundle(fhir.load_bundle(b)))
    store.omop_transform(conn)
    yield conn, path
    conn.close()


# ── parsing (no database) ─────────────────────────────────────────────────────

def test_parse_golden_bundle_matches_hub_contract():
    p = fhir.parse_bundle(fhir.load_bundle(GOLDEN))
    assert p.patient_id == "example-patient"
    assert p.report_id == "rpt-2026-09-04"
    assert len(p.observations) == 7
    # Same key the Hub's storeReportRows builds: patient-report-index
    assert p.observations[0]["resourceId"] == "example-patient-rpt-2026-09-04-1"
    hba1c = next(o for o in p.observations if o["code"] == "4548-4")
    assert hba1c["valueQuantity"] == 5.4 and hba1c["unit"] == "%"
    assert hba1c["sourceKind"] == "ocr-transcribed"
    assert hba1c["verifiedByPatientAt"] == "2026-09-05T08:01:00Z"


def test_unmapped_value_keeps_reason_and_no_fake_code():
    p = fhir.parse_bundle(fhir.load_bundle(GOLDEN))
    microbe = next(o for o in p.observations if o["display"] == "Akkermansia muciniphila")
    assert microbe["code"] is None
    assert "NCBI Taxonomy" in microbe["unmappedReason"]
    assert microbe["taxonCode"] == "239935"
    assert microbe["hubEligible"] is False


def test_hub_eligibility_follows_app_record_rules():
    digital = fhir.parse_bundle(fhir.load_bundle(BUNDLES[0]))  # lab-issued-digital -> final
    assert {o["status"] for o in digital.observations} == {"final"}
    assert not any(o["hubEligible"] for o in digital.observations)
    ocr = fhir.parse_bundle(fhir.load_bundle(GOLDEN))
    assert sum(o["hubEligible"] for o in ocr.observations) == 6


# ── graph ─────────────────────────────────────────────────────────────────────

def test_counts(db):
    conn, _ = db
    stats = {r["label"]: r["n"] for r in q(conn, "stats")}
    assert stats["Observation"] == 21
    assert stats["DiagnosticReport"] == 3
    assert stats["LoincCode"] == 6
    assert stats["OMOPMeasurement"] == 18  # 6 coded numeric values x 3 reports
    assert stats["Patient"] == 1 and stats["OMOPPerson"] == 1


def test_reimport_replaces_instead_of_duplicating(db):
    conn, _ = db
    store.import_report(conn, fhir.parse_bundle(fhir.load_bundle(GOLDEN)))
    store.omop_transform(conn)
    stats = {r["label"]: r["n"] for r in q(conn, "stats")}
    assert stats["Observation"] == 21
    assert stats["OMOPMeasurement"] == 18


def test_trend_is_ordered_with_provenance(db):
    conn, _ = db
    rows = q(conn, "trend", loinc="4548-4")
    assert [r["date"] for r in rows] == ["2026-03-12", "2026-06-10", "2026-09-04"]
    assert [r["value"] for r in rows] == ["5.9", "5.6", "5.4"]
    assert rows[0]["source"] == "lab-issued-digital"


def test_comparator_survives(db):
    conn, _ = db
    rows = q(conn, "trend", loinc="2276-4")
    assert rows[-1]["value"] == "<10"


def test_unmapped_query(db):
    conn, _ = db
    rows = q(conn, "unmapped")
    assert len(rows) == 3 and all(r["ncbiTaxon"] == "239935" for r in rows)


def test_provenance_shows_ocr_correction(db):
    conn, _ = db
    (row,) = q(conn, "provenance", resourceId="example-patient-rpt-2026-09-04-7")
    assert row["label"] == "Körpergewicht" and row["value"] == 80
    assert row["correctedFrom"] == "Körpergewicht 30 kg"
    assert row["document"] == "laborbefund-2026-09-04.pdf"


@pytest.mark.parametrize("term,label", [("Ferritin", "Ferritin"), ("cholesterol", "LDL-Cholesterin"),
                                        ("weight", "Körpergewicht"), ("Körpergewicht", "Körpergewicht")])
def test_fulltext_search_german_labels_and_loinc_names(db, term, label):
    conn, _ = db
    rows = q(conn, "search", q=term)
    assert rows and rows[0]["label"] == label


def test_omop_rows_use_concept_zero_and_loinc_source_value(db):
    conn, _ = db
    rows = q(conn, "omop")
    assert len(rows) == 18
    assert {r["conceptId"] for r in rows} == {0}
    assert {"4548-4", "2089-1"} <= {r["loinc"] for r in rows}


@pytest.mark.skipif(shutil.which("relate") is None, reason="relate CLI not on PATH")
def test_store_opens_read_only_from_cli(db):
    conn, path = db
    conn.close()
    out = subprocess.run(
        ["relate", "--database", str(path), "--read-only", "--mode", "envelope",
         "MATCH (o:Observation) RETURN count(o) AS n"],
        capture_output=True, text=True, check=True)
    assert '"n":21' in out.stdout.replace(" ", "")
