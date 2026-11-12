"""Write parsed reports into a local Relate store (.rl file)."""
from __future__ import annotations

from pathlib import Path

import relate

from .fhir import WEARABLE_SOURCE_REPORT, ParsedReport

HERE = Path(__file__).parent


def statements(path: Path) -> list[str]:
    """Split a .cypher file into statements (on ';'), dropping // comments."""
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    return [s.strip() for s in text.split(";") if s.strip()]


def connect(db: str | Path, read_only: bool = False) -> relate.Connection:
    return relate.connect(str(db), read_only=read_only) if read_only else relate.connect(str(db))


def init_schema(conn) -> None:
    for stmt in statements(HERE / "schema.cypher"):
        conn.execute(stmt)


# A report sent again replaces its earlier values (same rule as the Hub's
# storeReportRows), so imports are idempotent.
DELETE_REPORT = """
MATCH (o:Observation {sourceReport: $reportId})
OPTIONAL MATCH (o)-[:MAPPED_TO]->(om:OMOPMeasurement)
DETACH DELETE om, o
"""

UPSERT_REPORT = """
MERGE (p:Patient {id: $patientId})
MERGE (dr:DiagnosticReport {resourceId: $report.resourceId})
SET dr += $report
MERGE (p)-[:HAS_DIAGNOSTIC_REPORT]->(dr)
WITH p, dr
CALL (dr) {
  WITH dr WHERE $report.performer IS NOT NULL
  MERGE (org:Organization {name: $report.performer})
  MERGE (dr)-[:PERFORMED_BY]->(org)
}
CALL (dr) {
  WITH dr WHERE $document IS NOT NULL
  MERGE (doc:DocumentReference {resourceId: $document.resourceId})
  SET doc += $document
  MERGE (dr)-[:DERIVED_FROM]->(doc)
}
CALL (dr) {
  WITH dr WHERE $provenance IS NOT NULL
  MERGE (pv:Provenance {resourceId: $provenance.resourceId})
  SET pv += $provenance
  MERGE (pv)-[:TARGET]->(dr)
}
RETURN dr.resourceId AS report
"""

UPSERT_OBSERVATIONS = """
MATCH (p:Patient {id: $patientId})
MATCH (dr:DiagnosticReport {resourceId: $reportResourceId})
UNWIND $rows AS r
MERGE (o:Observation {resourceId: r.resourceId})
SET o += r, o.sourceReport = $reportId, o.contributedBy = 'klarbefund-app'
MERGE (p)-[:HAS_OBSERVATION]->(o)
MERGE (dr)-[:HAS_RESULT]->(o)
WITH o, r
CALL (o, r) {
  WITH o, r WHERE r.code IS NOT NULL
  MERGE (lc:LoincCode {code: r.code})
  ON CREATE SET lc.display = r.loincDisplay
  MERGE (o)-[:CODED_BY]->(lc)
}
CALL (o, r) {
  WITH o, r WHERE r.taxonCode IS NOT NULL
  MERGE (t:NcbiTaxon {code: r.taxonCode})
  ON CREATE SET t.display = r.taxonDisplay
  MERGE (o)-[:IDENTIFIES]->(t)
}
RETURN count(o) AS stored
"""


# The same measurement in two reports (one sheet scanned twice, or one result
# printed on two documents of the same visit) is one measurement: the same test
# (LOINC code, or the printed label when there is none), day, value, comparator
# and unit. One copy is kept, preferring the laboratory's own digital file over
# a scan; every other copy gets `duplicateOf` and a SAME_AS link to it. Nothing
# is deleted, so where each copy came from stays visible. Recomputed for the
# whole graph after every report, because a new report can change which copy
# is kept. Apple Health weekly means are a different series and never match.
UNLINK_SAME_MEASUREMENTS = """
MATCH (o:Observation) WHERE o.duplicateOf IS NOT NULL
OPTIONAL MATCH (o)-[s:SAME_AS]->()
DELETE s
REMOVE o.duplicateOf
RETURN count(DISTINCT o) AS cleared
"""

LINK_SAME_MEASUREMENTS = """
MATCH (o:Observation)
WHERE coalesce(o.sourceKind, '') <> 'device-weekly-mean'
  AND o.valueQuantity IS NOT NULL AND o.effectiveDate IS NOT NULL
WITH o, coalesce(o.code, 'label:' + toLower(trim(o.display))) AS measure,
     CASE o.sourceKind WHEN 'lab-issued-digital' THEN 0 WHEN 'ocr-transcribed' THEN 1 ELSE 2 END AS rank
ORDER BY rank, o.resourceId
WITH measure, left(o.effectiveDate, 10) AS day, o.valueQuantity AS value,
     coalesce(o.comparator, '') AS comparator, coalesce(o.unit, '') AS unit, collect(o) AS same
WHERE size(same) > 1
WITH head(same) AS kept, tail(same) AS copies
UNWIND copies AS copy
SET copy.duplicateOf = kept.resourceId
MERGE (copy)-[:SAME_AS]->(kept)
RETURN count(copy) AS duplicates
"""


def link_same_measurements(conn) -> int:
    conn.execute(UNLINK_SAME_MEASUREMENTS)
    return conn.execute(LINK_SAME_MEASUREMENTS).single()["duplicates"]


def import_report(conn, parsed: ParsedReport) -> int:
    conn.autocommit = False
    try:
        conn.execute(DELETE_REPORT, {"reportId": parsed.report_id})
        conn.execute(UPSERT_REPORT, {
            "patientId": parsed.patient_id,
            "report": parsed.report,
            "document": parsed.document,
            "provenance": parsed.provenance,
        })
        stored = conn.execute(UPSERT_OBSERVATIONS, {
            "patientId": parsed.patient_id,
            "reportId": parsed.report_id,
            "reportResourceId": parsed.report["resourceId"],
            "rows": parsed.observations,
        }).single()["stored"]
        link_same_measurements(conn)
        conn.commit()
        return stored
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


REPLACE_WEARABLES = """
MERGE (p:Patient {id: $patientId})
WITH p
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(old:Observation {sourceReport: $source})
OPTIONAL MATCH (old)-[:MAPPED_TO]->(om:OMOPMeasurement)
DETACH DELETE om, old
"""

UPSERT_WEARABLES = """
MATCH (p:Patient {id: $patientId})
UNWIND $rows AS r
MERGE (o:Observation {resourceId: r.resourceId})
SET o += r, o.sourceReport = $source, o.contributedBy = 'klarbefund-app'
MERGE (p)-[:HAS_OBSERVATION]->(o)
MERGE (lc:LoincCode {code: r.code})
ON CREATE SET lc.display = r.loincDisplay
MERGE (o)-[:CODED_BY]->(lc)
RETURN count(o) AS stored
"""


def import_wearables(conn, patient_id: str, rows: list[dict]) -> int:
    """Replace the patient's Apple Health weekly means (same rule as the Hub)."""
    conn.autocommit = False
    try:
        params = {"patientId": patient_id, "source": WEARABLE_SOURCE_REPORT}
        conn.execute(REPLACE_WEARABLES, params)
        stored = conn.execute(UPSERT_WEARABLES, {**params, "rows": rows}).single()["stored"] if rows else 0
        conn.commit()
        return stored
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def single_patient(conn, default: str = "meinbefund-local") -> str:
    ids = [r["id"] for r in conn.execute("MATCH (p:Patient) RETURN p.id AS id")]
    return ids[0] if len(ids) == 1 else default


def omop_transform(conn) -> dict[str, int]:
    """Run the local FHIR -> OMOP CDM v5.4 transform (idempotent)."""
    counts = {}
    for stmt in statements(HERE / "omop.cypher"):
        rec = conn.execute(stmt).single()
        if rec:
            counts.update(dict(rec))
    return counts
