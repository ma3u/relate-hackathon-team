"""The knowledge layer of the graph: what the measurements mean together.

Static, sourced facts, the same for everyone, seeded into the graph next to the
person's values so that one Cypher query can walk from a health risk to the
scores that estimate it, to the measures they use, to the person's values and
the ranges those values sit in.

    (:HealthRisk)<-[:ESTIMATES]-(:RiskScore)-[:USES]->(:LoincCode)
    (:LoincCode)-[:MARKER_OF {source}]->(:HealthRisk)
    (:ReferenceRange)-[:APPLIES_TO]->(:LoincCode)        guideline range + optimal band
    (:Patient)-[:HAS_SCORE]->(:ScoreResult)-[:OF]->(:RiskScore)
    (:ScoreResult)-[:FROM]->(:Observation)              the exact values a score used

Reference ranges come from Klarbefund's reference-ranges.ts (exported with
`npm run export:reference-ranges` in MinimumViableHealthDataspacev2) and are
quoted, never edited. Every marker link names the guideline that makes it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent

LDL = ["22748-8", "13457-7", "18262-6", "2089-1"]
TC = ["14647-2", "2093-3"]
HDL = ["14646-4", "2085-9"]
TG = ["14927-8", "2571-8"]
GLUCOSE = ["2345-7", "1558-6"]
HBA1C = ["4548-4", "59261-8"]

HEALTH_RISKS = [
    {"id": "cardiovascular", "name": "Cardiovascular disease",
     "description": "Heart attack, stroke and other diseases of the heart and arteries."},
    {"id": "diabetes", "name": "Type 2 diabetes",
     "description": "Raised blood sugar from insulin resistance and failing insulin secretion."},
    {"id": "kidney", "name": "Chronic kidney disease",
     "description": "A lasting fall in kidney filtration or damage to the kidneys."},
    {"id": "liver", "name": "Liver fibrosis",
     "description": "Scarring of the liver, most often from fatty liver disease or alcohol."},
    {"id": "fitness", "name": "Low cardiorespiratory fitness",
     "description": "Low aerobic capacity, one of the strongest predictors of mortality."},
]

RISK_SCORES = [
    {"id": "score2", "name": "SCORE2", "estimates": "cardiovascular", "unit": "%",
     "uses": TC + HDL + ["8480-6"], "demographics": "age, sex, smoking",
     "source": "SCORE2 working group, Eur Heart J 2021;42:2439"},
    {"id": "egfr", "name": "eGFR (CKD-EPI 2021)", "estimates": "kidney", "unit": "mL/min/1.73 m2",
     "uses": ["2160-0"], "demographics": "age, sex", "source": "Inker et al., N Engl J Med 2021;385:1737"},
    {"id": "fib4", "name": "FIB-4", "estimates": "liver", "unit": "",
     "uses": ["1920-8", "1742-6", "777-3"], "demographics": "age",
     "source": "Sterling et al., Hepatology 2006;43:1317"},
    {"id": "tyg", "name": "TyG index", "estimates": "diabetes", "unit": "",
     "uses": TG + ["1558-6"], "demographics": "",
     "source": "Simental-Mendía et al., Metab Syndr Relat Disord 2008;6:299"},
]

ESC_LIPIDS = "ESC/EAS 2019 dyslipidaemia guideline"
ESC_PREV = "ESC 2021 cardiovascular prevention guideline"
MARKERS = [  # (LOINC codes, risk id, source)
    (LDL, "cardiovascular", ESC_LIPIDS), (TC, "cardiovascular", ESC_PREV), (HDL, "cardiovascular", ESC_PREV),
    (["1884-6"], "cardiovascular", ESC_LIPIDS), (["10835-7"], "cardiovascular", "EAS consensus statement 2022"),
    (TG, "cardiovascular", ESC_LIPIDS), (["8480-6", "8462-4"], "cardiovascular", "ESC 2024 hypertension guideline"),
    (["30522-7"], "cardiovascular", ESC_PREV), (["33762-6"], "cardiovascular", "ESC 2021 heart failure guideline"),
    (HBA1C + GLUCOSE, "diabetes", "ADA Standards of Care 2024"), (TG + HDL, "diabetes", "IDF metabolic syndrome definition 2006"),
    (["39156-5", "8280-0", "29463-7"], "diabetes", "ADA Standards of Care 2024"),
    (["39156-5", "8280-0"], "cardiovascular", ESC_PREV),
    (["2160-0"], "kidney", "KDIGO 2012 CKD guideline"), (["8480-6"], "kidney", "KDIGO 2021 blood pressure guideline"),
    (HBA1C, "kidney", "KDIGO 2022 diabetes in CKD guideline"),
    (["1920-8", "1742-6", "777-3"], "liver", "EASL 2021 non-invasive tests guideline"),
    (["2324-2"], "liver", "EASL 2021 non-invasive tests guideline"), (TG + ["39156-5"], "liver", "EASL-EASD-EASO 2024 MASLD guideline"),
    (["94122-9"], "fitness", "Kodama et al., JAMA 2009;301:2024"), (["40443-4"], "fitness", "Kodama et al., JAMA 2009;301:2024"),
    (["94122-9", "40443-4"], "cardiovascular", "AHA scientific statement on cardiorespiratory fitness, Circulation 2016"),
    (["80404-7"], "fitness", "Task Force of the ESC and NASPE, Circulation 1996 (HRV standards)"),
    (["41950-7"], "fitness", "Paluch et al., Lancet Public Health 2022 (daily steps and mortality)"),
]


def reference_ranges() -> list[dict]:
    return json.loads((HERE / "reference_ranges.json").read_text(encoding="utf-8"))["ranges"]


def _range_rows() -> list[dict]:
    rows = []
    for r in reference_ranges():
        if not r.get("loinc"):
            continue
        rows.append({
            "id": f"{r['analyteKey']}|{r['ucum']}|{r['sex']}", "loinc": r["loinc"],
            "analyteKey": r["analyteKey"], "ucum": r["ucum"], "sex": r["sex"], "group": r["group"],
            "guidelineLow": r.get("guidelineLow"), "guidelineHigh": r.get("guidelineHigh"),
            "optimalLow": r.get("optimalLow"), "optimalHigh": r.get("optimalHigh"),
            "basis": r["basis"], "summary": r["summary"],
            "sourceLabel": r["source"]["label"], "sourceUrl": r["source"]["url"],
        })
    return rows


def _marker_rows() -> list[dict]:
    return [{"loinc": code, "risk": risk, "source": source} for codes, risk, source in MARKERS for code in codes]


def fingerprint() -> str:
    """Changes whenever any seeded fact changes, so seeding runs only then."""
    blob = json.dumps([HEALTH_RISKS, RISK_SCORES, _marker_rows(), _range_rows()], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


SEED_RISKS = """
UNWIND $risks AS r
MERGE (h:HealthRisk {id: r.id})
SET h.name = r.name, h.description = r.description
RETURN count(h) AS risks
"""

SEED_SCORES = """
UNWIND $scores AS s
MERGE (rs:RiskScore {id: s.id})
SET rs.name = s.name, rs.unit = s.unit, rs.source = s.source, rs.demographics = s.demographics
WITH rs, s
MATCH (h:HealthRisk {id: s.estimates})
MERGE (rs)-[:ESTIMATES]->(h)
WITH rs, s
UNWIND s.uses AS code
MERGE (lc:LoincCode {code: code})
MERGE (rs)-[:USES]->(lc)
RETURN count(DISTINCT rs) AS scores
"""

SEED_MARKERS = """
UNWIND $markers AS m
MATCH (h:HealthRisk {id: m.risk})
MERGE (lc:LoincCode {code: m.loinc})
MERGE (lc)-[k:MARKER_OF]->(h)
SET k.source = m.source
RETURN count(k) AS markers
"""

SEED_RANGES = """
UNWIND $ranges AS r
MERGE (rr:ReferenceRange {id: r.id})
SET rr += r
WITH rr, r
MERGE (lc:LoincCode {code: r.loinc})
MERGE (rr)-[:APPLIES_TO]->(lc)
RETURN count(rr) AS ranges
"""

SEED_VERSION = """
MERGE (k:Knowledge {id: 'health-graph'})
SET k.fingerprint = $fingerprint, k.rangesSource = $rangesSource
RETURN k.fingerprint AS fingerprint
"""


def seed(conn, force: bool = False) -> dict[str, int]:
    """Writes the knowledge layer; a no-op when it is already current."""
    rows = list(conn.execute("MATCH (k:Knowledge {id: 'health-graph'}) RETURN k.fingerprint AS f"))
    fp = fingerprint()
    if rows and rows[0]["f"] == fp and not force:
        return {}
    conn.autocommit = False
    try:
        counts = {}
        counts.update(dict(conn.execute(SEED_RISKS, {"risks": HEALTH_RISKS}).single()))
        counts.update(dict(conn.execute(SEED_SCORES, {"scores": RISK_SCORES}).single()))
        counts.update(dict(conn.execute(SEED_MARKERS, {"markers": _marker_rows()}).single()))
        counts.update(dict(conn.execute(SEED_RANGES, {"ranges": _range_rows()}).single()))
        source = json.loads((HERE / "reference_ranges.json").read_text())["source"]
        conn.execute(SEED_VERSION, {"fingerprint": fp, "rangesSource": source})
        conn.commit()
        return counts
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


# ── the person's score results, with the values they used ────────────────────
STORE_SCORE = """
MATCH (p:Patient {id: $patientId})
MATCH (rs:RiskScore {id: $score})
MERGE (sr:ScoreResult {id: $patientId + '-' + $score})
SET sr.value = $value, sr.unit = rs.unit, sr.band = $band, sr.light = $light,
    sr.computedAt = $computedAt, sr.demographics = $demographics, sr.note = $note
MERGE (p)-[:HAS_SCORE]->(sr)
MERGE (sr)-[:OF]->(rs)
WITH sr
OPTIONAL MATCH (sr)-[old:FROM]->()
DELETE old
WITH DISTINCT sr
UNWIND $inputs AS input
MATCH (o:Observation {resourceId: input})
MERGE (sr)-[:FROM]->(o)
RETURN count(o) AS inputs
"""


def store_score(conn, patient_id: str, score: str, value: float, band: str | None, light: str | None,
                inputs: list[str], demographics: str, note: str | None, computed_at: str) -> int:
    rec = conn.execute(STORE_SCORE, {
        "patientId": patient_id, "score": score, "value": value, "band": band, "light": light,
        "inputs": inputs, "demographics": demographics, "note": note, "computedAt": computed_at,
    }).single()
    return rec["inputs"] if rec else 0
