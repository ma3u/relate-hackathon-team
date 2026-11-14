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


def test_unmapped_value_from_klarbefund_local_export():
    """LocalGraphExport.swift adds uncoded Observations: label, raw unit, reason."""
    bundle = fhir.load_bundle(GOLDEN)
    report = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "DiagnosticReport")
    bundle["entry"].append({"resource": {
        "resourceType": "Observation", "id": "unmapped-1", "status": "preliminary",
        "extension": [{"url": fhir.EXT + "source-kind", "valueCode": "ocr-transcribed"},
                      {"url": fhir.EXT + "source-line", "valueString": "Zonulin  >48,2  ng/ml  < 55"}],
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
        "code": {"text": "Zonulin", "extension": [{"url": fhir.DATA_ABSENT, "valueCode": "unknown",
                 "_valueCode": {"extension": [{"url": fhir.RENDERED, "valueString": "Not coded: not in the analyte dictionary"}]}}]},
        "subject": {"reference": "Patient/example-patient"}, "effectiveDateTime": "2026-09-04",
        "valueQuantity": {"value": 48.2, "unit": "ng/ml", "comparator": ">"},
        "referenceRange": [{"high": {"value": 55, "unit": "ng/ml"}, "text": "< 55"}]}})
    report["result"].append({"reference": "Observation/unmapped-1"})
    p = fhir.parse_bundle(bundle)
    z = p.observations[-1]
    assert z["code"] is None and z["display"] == "Zonulin"
    assert z["unmappedReason"] == "Not coded: not in the analyte dictionary"
    assert z["valueQuantity"] == 48.2 and z["unit"] == "ng/ml" and z["comparator"] == ">"
    assert z["hubEligible"] is False
    # coded values keep their Hub-compatible ids; the new one comes after them
    assert p.observations[0]["resourceId"].endswith("-1") and z["resourceId"].endswith("-8")


# ── duplicates (Nov 12, 2026: one sheet scanned twice, repeats on one report) ──

def _observations(bundle):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]


def _as_digital(bundle):
    for o in _observations(bundle):
        for x in o.get("extension", []):
            if x["url"].endswith("source-kind"):
                x["valueCode"] = "lab-issued-digital"
    return bundle


def test_a_value_printed_twice_on_one_report_is_one_value():
    import copy
    bundle = fhir.load_bundle(GOLDEN)
    first = _observations(bundle)[5]  # Akkermansia: overview table and detail section
    again = copy.deepcopy(first)
    again["id"] = "obs-6-again"
    bundle["entry"].append({"resource": again})
    parsed = fhir.parse_bundle(bundle)
    assert len(parsed.observations) == 7
    folded = [o for o in parsed.observations if o["fhirId"] == first["id"]][0]
    assert folded["repeatedOnReport"] == 2


def test_the_same_report_twice_counts_each_measurement_once(db):
    conn, _ = db
    store.import_report(conn, fhir.parse_bundle(_as_digital(fhir.load_bundle(GOLDEN)), report_id="rescan"))
    store.omop_transform(conn)
    stats = {r["label"]: r["n"] for r in q(conn, "stats")}
    assert stats["Observation"] == 28  # nothing deleted
    assert stats["OMOPMeasurement"] == 18  # but measured once
    dups = q(conn, "duplicates")
    assert len(dups) == 7
    assert {d["keptSource"] for d in dups} == {"lab-issued-digital"}  # the lab's own file wins
    trend = q(conn, "trend", loinc="4548-4")
    assert [r["date"] for r in trend] == ["2026-03-12", "2026-06-10", "2026-09-04"]
    assert trend[-1]["alsoInOtherReports"] == 1
    hba1c = [r for r in q(conn, "analytes") if r["loinc"] == "4548-4"][0]
    assert hba1c["n"] == 3
    per_report = {r["date"][:10] + str(r["alsoInAnotherReport"]) for r in q(conn, "reports")}
    assert "2026-09-047" in per_report


def test_removing_the_copy_restores_the_first(db):
    conn, _ = db
    rescan = fhir.parse_bundle(_as_digital(fhir.load_bundle(GOLDEN)), report_id="rescan")
    store.import_report(conn, rescan)
    conn.execute(store.DELETE_REPORT, {"reportId": "rescan"})
    store.link_same_measurements(conn)
    store.omop_transform(conn)
    assert q(conn, "duplicates") == []
    assert {r["label"]: r["n"] for r in q(conn, "stats")}["OMOPMeasurement"] == 18


# ── year of birth and sex (Klarbefund's opt-in "Send year of birth and sex") ──

def test_year_of_birth_and_sex_reach_patient_and_omop(tmp_path):
    bundle = fhir.load_bundle(GOLDEN)
    patient = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Patient")
    patient["birthDate"] = "1971-05-03"  # a full date is cut to the year
    patient["gender"] = "male"
    parsed = fhir.parse_bundle(bundle)
    assert parsed.patient == {"birthYear": 1971, "gender": "male"}
    conn = store.connect(tmp_path / "h.rl")
    store.init_schema(conn)
    store.import_report(conn, parsed)
    store.omop_transform(conn)
    p = conn.execute("MATCH (p:Patient) RETURN p.birthYear AS y, p.gender AS g, keys(p) AS k").single()
    assert (p["y"], p["g"]) == (1971, "male")
    assert "birthDate" not in p["k"]
    op = conn.execute("MATCH (op:OMOPPerson) RETURN op.yearOfBirth AS y, op.genderConceptId AS g").single()
    assert (op["y"], op["g"]) == (1971, 8507)
    conn.close()


def test_without_the_switch_nothing_about_the_person_is_stored():
    assert fhir.parse_bundle(fhir.load_bundle(GOLDEN)).patient == {}


# ── knowledge layer: reference ranges, risks, scores, markers ─────────────────

def test_knowledge_is_seeded_once_and_links_ranges_to_loinc(db):
    from health_graph import knowledge
    conn, _ = db
    counts = knowledge.seed(conn)
    assert counts["ranges"] == len([r for r in knowledge.reference_ranges() if r["loinc"]])
    assert counts["risks"] == 6 and counts["scores"] == 4
    assert knowledge.seed(conn) == {}  # already current: nothing written
    ldl = conn.execute("""MATCH (rr:ReferenceRange {analyteKey: 'cholesterol-ldl', ucum: 'mmol/L'})
                          -[:APPLIES_TO]->(lc:LoincCode) RETURN rr.guidelineHigh AS g, rr.optimalHigh AS o,
                          lc.code AS code, rr.sourceLabel AS src""").single()
    assert (ldl["g"], ldl["o"], ldl["code"]) == (3.0, 1.4, "22748-8") and ldl["src"]
    walk = conn.execute("""MATCH (h:HealthRisk {id: 'cardiovascular'})<-[:ESTIMATES]-(:RiskScore {id: 'score2'})
                           -[:USES]->(lc:LoincCode) RETURN count(DISTINCT lc) AS n""").single()["n"]
    assert walk == 5  # total cholesterol and HDL in two units each, systolic BP


def test_ranges_are_versioned_and_sourced(db):
    from health_graph import knowledge
    conn, _ = db
    conn.execute("CREATE (:ReferenceRange {id: 'cholesterol-ldl|mmol/L|any'})")  # a key from before editions
    counts = knowledge.seed(conn)
    assert counts["prunedRanges"] == 1
    unsourced = conn.execute("MATCH (rr:ReferenceRange) WHERE NOT (rr)-[:SOURCED_FROM]->(:Study) "
                             "RETURN count(rr) AS n").single()["n"]
    assert unsourced == 0
    vit = conn.execute("""MATCH (rr:ReferenceRange {analyteKey: 'vitamin-d', ucum: 'ng/mL'})-[:SOURCED_FROM]->(st)
                          RETURN rr.validUntil AS until, rr.supersededBy AS by, st.pmid AS pmid, st.url AS doi""").single()
    assert vit["until"] == "2024-06-03" and "38828931" in vit["by"]
    assert vit["pmid"] == "21646368" and vit["doi"] == "https://doi.org/10.1210/jc.2011-0385"
    # every range with a PubMed source reaches PubMed and a DOI
    missing = conn.execute("""MATCH (rr:ReferenceRange)-[:SOURCED_FROM]->(st:Study)
                              WHERE rr.sourcePmid IS NOT NULL AND (st.pubmedUrl IS NULL OR st.url IS NULL)
                              RETURN count(rr) AS n""").single()["n"]
    assert missing == 0
    # one paper, one Study node: no DOI under two ids
    dois = [s["url"] for s in knowledge.STUDIES] + [s["url"] for s in knowledge._range_source_rows()]
    assert len(dois) == len(set(dois))


def test_risk_links_name_their_studies(db):
    from health_graph import knowledge
    from health_graph.queries import QUERIES
    conn, _ = db
    counts = knowledge.seed(conn)
    assert counts["studies"] == len(knowledge.STUDIES) and counts["riskLinks"] == len(knowledge.RISK_LINKS)
    ids = {s["id"] for s in knowledge.STUDIES}
    assert all(set(link["studies"]) <= ids for link in knowledge.RISK_LINKS)  # no dangling citation
    rows = list(conn.execute(QUERIES["risk_links"][1]))
    assert len(rows) == len(knowledge.RISK_LINKS)
    liver = next(r for r in rows if r["risk"] == "Liver fibrosis" and r["raisesRiskOf"] == "Type 2 diabetes")
    assert liver["estimate"] == 2.19 and liver["studies"] and all(liver["studies"])
    assert all(r["studies"] for r in rows)  # every link reaches at least one Study
    assert counts["studyMarkers"] == len(knowledge._examines_rows()) and counts["studyScores"] == 11
    assert counts["citations"] == len(knowledge.STUDY_CITATIONS)  # every cited id is a Study we seed
    kinds = {r["k"]: r["n"] for r in conn.execute("MATCH (s:Study) RETURN s.kind AS k, count(s) AS n")}
    sources = {s["id"] for s in knowledge.STUDIES} | {s["id"] for s in knowledge._range_source_rows()}
    assert set(kinds) == {"study", "guideline"} and sum(kinds.values()) == len(sources) == 48
    assert counts["studyRisks"] == len(knowledge.STUDY_ABOUT)  # every id there is a Study we seed
    newer = list(conn.execute("MATCH (s:Study {id: 'esc-eas-2025-lipids'})-[:ABOUT]->(h:HealthRisk) RETURN h.id AS h"))
    assert [r["h"] for r in newer] == ["cardiovascular"]
    assert conn.execute("MATCH (s:Study) WHERE size(s.topics) = 0 RETURN count(s) AS n").single()["n"] == 0
    hba1c = list(conn.execute(QUERIES["evidence"][1], {"loinc": "4548-4"}))
    assert any(r["study"].startswith("SCORE2-Diabetes") and r["pubmed"].endswith("/37247330/") for r in hba1c)
    assert all(r["doi"].startswith("https://doi.org/") for r in hba1c)


def test_a_stored_score_points_at_the_values_it_used(db):
    from health_graph import knowledge
    conn, _ = db
    knowledge.seed(conn)
    obs = [r["id"] for r in conn.execute(
        "MATCH (o:Observation) RETURN o.resourceId AS id ORDER BY id LIMIT 2")]
    patient = conn.execute("MATCH (p:Patient) RETURN p.id AS id").single()["id"]
    assert knowledge.store_score(conn, patient, "fib4", 1.1, "below the low cut-off", "green", obs,
                                 "age 50", None, "2026-11-12T00:00:00+00:00") == 2
    assert knowledge.store_score(conn, patient, "fib4", 1.2, "below the low cut-off", "green", obs[:1],
                                 "age 50", None, "2026-11-13T00:00:00+00:00") == 1  # replaces, not adds
    n = conn.execute("MATCH (:Patient)-[:HAS_SCORE]->(sr:ScoreResult)-[:FROM]->(o) RETURN count(o) AS n, "
                     "max(sr.value) AS v").single()
    assert (n["n"], n["v"]) == (1, 1.2)


def test_lights_use_the_guideline_range_and_the_optimal_band():
    from health_graph import risk, scores
    ranges = {"22748-8": [{"sex": "any", "ucum": "mmol/L", "guidelineLow": None, "guidelineHigh": 3.0,
                           "optimalLow": None, "optimalHigh": 1.4, "sourceLabel": "ESC/EAS 2019"}]}
    point = lambda v: ("2026-01-01", v, "", "", None, None, "r1", "22748-8")
    assert risk.lab_light(ranges, point(1.2), "mmol/L", "male")[0] == scores.GREEN
    assert risk.lab_light(ranges, point(2.5), "mmol/L", "male")[0] == scores.AMBER
    assert risk.lab_light(ranges, point(3.0), "mmol/L", "male")[0] == scores.RED  # the target is "below 3.0"
    # in mg/dL the value converts exactly to the range's mmol/L
    assert risk.lab_light(ranges, point(50), "mg/dL", "male")[0] == scores.GREEN
    # no reference range: the range the laboratory printed decides, inside or outside
    lab = ("2026-01-01", 7.0, "", "", 1.0, 5.0, "r2", "9999-9")
    assert risk.lab_light(ranges, lab, "mg/L", None)[0] == scores.RED
