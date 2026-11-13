"""The knowledge layer of the graph: what the measurements mean together.

Static, sourced facts, the same for everyone, seeded into the graph next to the
person's values so that one Cypher query can walk from a health risk to the
scores that estimate it, to the measures they use, to the person's values and
the ranges those values sit in.

    (:HealthRisk)<-[:ESTIMATES]-(:RiskScore)-[:USES]->(:LoincCode)
    (:LoincCode)-[:MARKER_OF {source}]->(:HealthRisk)
    (:ReferenceRange)-[:APPLIES_TO]->(:LoincCode)        guideline range + optimal band
    (:ReferenceRange {validFrom, validUntil, supersededBy})-[:SOURCED_FROM]->(:Study)   edition and evidence
    (:HealthRisk)-[:RAISES_RISK_OF {summary, measure, estimate, ciLow, ciHigh, studies}]->(:HealthRisk)
    (:Study {citation, title, year, design, url, pmid, pubmedUrl})-[:ABOUT]->(:HealthRisk)   the evidence for a link
    (:Study)-[:EXAMINES]->(:LoincCode), (:Study)-[:INFORMS]->(:RiskScore)   the markers and scores it is about
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
NON_HDL = ["70204-3", "43396-1"]
EGFR_MEASURED = ["62238-1", "98979-8", "33914-3", "48642-3"]
VITAMIN_D = ["62292-8", "68438-1", "1989-3"]
UACR = ["9318-7", "14959-1"]
FIB4_INPUTS = ["1920-8", "1742-6", "777-3"]  # AST, ALT, platelets
BONE_MINERAL = ["17861-6", "2777-1", "2731-8", "6768-6"]  # calcium, phosphate, PTH, alkaline phosphatase

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
    {"id": "bone", "name": "Osteoporosis",
     "description": "Thin, fragile bones that break easily; vitamin D and calcium keep bone mineralised."},
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
    (["2160-0"], "kidney", "KDIGO 2012 CKD guideline"), (EGFR_MEASURED, "kidney", "KDIGO 2012 CKD guideline"),
    (NON_HDL, "cardiovascular", ESC_LIPIDS),
    (VITAMIN_D, "bone", "Endocrine Society clinical practice guideline on vitamin D, 2024"), (["8480-6"], "kidney", "KDIGO 2021 blood pressure guideline"),
    (HBA1C, "kidney", "KDIGO 2022 diabetes in CKD guideline"),
    (["1920-8", "1742-6", "777-3"], "liver", "EASL 2021 non-invasive tests guideline"),
    (["2324-2"], "liver", "EASL 2021 non-invasive tests guideline"), (TG + ["39156-5"], "liver", "EASL-EASD-EASO 2024 MASLD guideline"),
    (["94122-9"], "fitness", "Kodama et al., JAMA 2009;301:2024"), (["40443-4"], "fitness", "Kodama et al., JAMA 2009;301:2024"),
    (["94122-9", "40443-4"], "cardiovascular", "AHA scientific statement on cardiorespiratory fitness, Circulation 2016"),
    (["80404-7"], "fitness", "Task Force of the ESC and NASPE, Circulation 1996 (HRV standards)"),
    (["41950-7"], "fitness", "Paluch et al., Lancet Public Health 2022 (daily steps and mortality)"),
]

# How the risks drive each other, from meta-analyses, pooled cohorts and
# guidelines. Every link names its studies; the estimate is the study's own
# (observational: an association, not proof of cause), None where a guideline
# states the link without one number.
STUDIES = [
    {"id": "mantovani-2021-cvd", "year": 2021, "design": "meta-analysis, 36 cohorts, 5.8 million adults",
     "citation": "Mantovani et al., Lancet Gastroenterol Hepatol 2021;6:903",
     "title": "Non-alcoholic fatty liver disease and risk of fatal and non-fatal cardiovascular events",
     "url": "https://doi.org/10.1016/S2468-1253(21)00308-3",
     "pmid": "34555346", "examines": FIB4_INPUTS, "informs": ["fib4"]},
    {"id": "mantovani-2021-t2d", "year": 2021, "design": "meta-analysis, 33 studies, 501,022 adults",
     "citation": "Mantovani et al., Gut 2021;70:962",
     "title": "Non-alcoholic fatty liver disease and risk of incident diabetes mellitus",
     "url": "https://doi.org/10.1136/gutjnl-2020-322572",
     "pmid": "32938692", "examines": HBA1C + GLUCOSE, "informs": ["fib4"]},
    {"id": "mantovani-2022-ckd", "year": 2022, "design": "meta-analysis of cohort studies",
     "citation": "Mantovani et al., Gut 2022;71:156",
     "title": "Non-alcoholic fatty liver disease and risk of incident chronic kidney disease",
     "url": "https://doi.org/10.1136/gutjnl-2020-323082",
     "pmid": "33303564", "examines": ["2160-0"] + UACR, "informs": ["egfr"]},
    {"id": "erfc-2010", "year": 2010, "design": "pooled analysis, 102 prospective studies, 698,782 people",
     "citation": "Emerging Risk Factors Collaboration, Lancet 2010;375:2215",
     "title": "Diabetes mellitus, fasting blood glucose concentration, and risk of vascular disease",
     "url": "https://doi.org/10.1016/S0140-6736(10)60484-9",
     "pmid": "20609967", "examines": GLUCOSE, "informs": []},
    {"id": "score2-diabetes-2023", "year": 2023, "design": "risk model, 229,460 people with type 2 diabetes",
     "citation": "SCORE2-Diabetes Working Group, Eur Heart J 2023;44:2544",
     "title": "SCORE2-Diabetes: 10-year cardiovascular risk estimation in type 2 diabetes in Europe",
     "url": "https://doi.org/10.1093/eurheartj/ehad260",
     "pmid": "37247330", "examines": TC + HDL + ["8480-6", "2160-0"] + HBA1C, "informs": ["score2", "egfr"]},
    {"id": "ckm-2023", "year": 2023, "design": "AHA presidential advisory",
     "citation": "Ndumele et al., Circulation 2023;148:1606",
     "title": "Cardiovascular-Kidney-Metabolic Health: A Presidential Advisory From the American Heart Association",
     "url": "https://doi.org/10.1161/CIR.0000000000001184",
     "pmid": "37807924", "examines": HBA1C + ["2160-0"] + UACR + TG + HDL + ["39156-5", "8280-0"], "informs": ["egfr"]},
    {"id": "kdigo-2022-diabetes", "year": 2022, "design": "clinical practice guideline",
     "citation": "KDIGO 2022 Clinical Practice Guideline for Diabetes Management in CKD, Kidney Int 2022;102:S1",
     "title": "KDIGO 2022 Clinical Practice Guideline for Diabetes Management in Chronic Kidney Disease",
     "url": "https://doi.org/10.1016/j.kint.2022.06.008",
     "pmid": "36272764", "examines": HBA1C + ["2160-0"] + UACR, "informs": ["egfr"]},
    {"id": "easl-2024-masld", "year": 2024, "design": "clinical practice guideline",
     "citation": "EASL-EASD-EASO, J Hepatol 2024;81:492",
     "title": "EASL-EASD-EASO Clinical Practice Guidelines on the management of MASLD",
     "url": "https://doi.org/10.1016/j.jhep.2024.04.031",
     "pmid": "38851997", "examines": FIB4_INPUTS + TG + ["39156-5", "8280-0"] + HBA1C, "informs": ["fib4"]},
    {"id": "ckdpc-2010", "year": 2010, "design": "collaborative meta-analysis of general population cohorts",
     "citation": "Chronic Kidney Disease Prognosis Consortium (Matsushita et al.), Lancet 2010;375:2073",
     "title": "Association of estimated glomerular filtration rate and albuminuria with all-cause and "
              "cardiovascular mortality in general population cohorts",
     "url": "https://doi.org/10.1016/S0140-6736(10)60674-5",
     "pmid": "20483451", "examines": ["2160-0"] + UACR, "informs": ["egfr"]},
    {"id": "prevent-2024", "year": 2024, "design": "risk model (AHA PREVENT), US adults 30-79",
     "citation": "Khan et al., Circulation 2024;149:430",
     "title": "Development and Validation of the American Heart Association's PREVENT Equations",
     "url": "https://doi.org/10.1161/CIRCULATIONAHA.123.067626",
     "pmid": "37947085", "examines": TC + HDL + ["8480-6", "2160-0"] + HBA1C + UACR, "informs": ["egfr"]},
    {"id": "kdigo-2017-mbd", "year": 2017, "design": "clinical practice guideline",
     "citation": "KDIGO 2017 CKD-MBD Guideline Update, Kidney Int Suppl 2017;7:1",
     "title": "KDIGO 2017 Clinical Practice Guideline Update for CKD-Mineral and Bone Disorder",
     "url": "https://doi.org/10.1016/j.kisu.2017.04.001",
     "pmid": "30675420", "examines": BONE_MINERAL + VITAMIN_D, "informs": ["egfr"]},
    {"id": "vestergaard-2007", "year": 2007, "design": "meta-analysis",
     "citation": "Vestergaard, Osteoporos Int 2007;18:427",
     "title": "Discrepancies in bone mineral density and fracture risk in patients with type 1 and type 2 diabetes",
     "url": "https://doi.org/10.1007/s00198-006-0253-4",
     "pmid": "17068657", "examines": HBA1C + ["39156-5"], "informs": []},
    {"id": "kodama-2009", "year": 2009, "design": "meta-analysis, 33 studies, 102,980 people",
     "citation": "Kodama et al., JAMA 2009;301:2024",
     "title": "Cardiorespiratory fitness as a quantitative predictor of all-cause mortality and cardiovascular "
              "events in healthy men and women",
     "url": "https://doi.org/10.1001/jama.2009.681",
     "pmid": "19454641", "examines": ["94122-9"], "informs": []},
]

# Names for codes only the studies bring in (the others are named by the lab values).
CODE_NAMES = {
    "9318-7": "Albumin/Creatinine [Mass Ratio] in Urine",
    "14959-1": "Microalbumin/Creatinine [Mass Ratio] in Urine",
    "17861-6": "Calcium [Mass/volume] in Serum or Plasma",
    "2777-1": "Phosphate [Mass/volume] in Serum or Plasma",
    "2731-8": "Parathyrin.intact [Mass/volume] in Serum or Plasma",
    "6768-6": "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma",
}

RISK_LINKS = [  # from risk raises the risk of to risk
    {"from": "liver", "to": "cardiovascular", "studies": ["mantovani-2021-cvd"],
     "measure": "HR, fatal or non-fatal cardiovascular events", "estimate": 1.45, "ciLow": 1.31, "ciHigh": 1.61,
     "summary": "Fatty liver disease goes with about 1.5 times the risk of heart attack and stroke; "
                "with liver fibrosis about 2.5 times (HR 2.50, 1.68-3.72)."},
    {"from": "liver", "to": "diabetes", "studies": ["mantovani-2021-t2d", "easl-2024-masld"],
     "measure": "HR, incident diabetes", "estimate": 2.19, "ciLow": 1.93, "ciHigh": 2.48,
     "summary": "Fatty liver disease about doubles the risk of developing diabetes; with fibrosis more than "
                "threefold (HR 3.42, 2.29-5.11)."},
    {"from": "liver", "to": "kidney", "studies": ["mantovani-2022-ckd"],
     "measure": "HR, incident CKD stage 3 or worse", "estimate": 1.43, "ciLow": 1.33, "ciHigh": 1.54,
     "summary": "Fatty liver disease goes with a moderately higher risk of chronic kidney disease."},
    {"from": "diabetes", "to": "cardiovascular", "studies": ["erfc-2010", "score2-diabetes-2023", "ckm-2023"],
     "measure": "HR, coronary heart disease", "estimate": 2.00, "ciLow": 1.83, "ciHigh": 2.19,
     "summary": "Diabetes about doubles the risk of coronary heart disease and ischaemic stroke; SCORE2-Diabetes "
                "adds HbA1c, eGFR and age at diagnosis to the estimate."},
    {"from": "diabetes", "to": "kidney", "studies": ["kdigo-2022-diabetes", "ckm-2023"],
     "measure": None, "estimate": None, "ciLow": None, "ciHigh": None,
     "summary": "Diabetes is a leading cause of chronic kidney disease; guidelines ask for yearly eGFR and urine "
                "albumin checks."},
    {"from": "diabetes", "to": "liver", "studies": ["easl-2024-masld"],
     "measure": None, "estimate": None, "ciLow": None, "ciHigh": None,
     "summary": "With type 2 diabetes the guideline recommends looking for liver fibrosis (FIB-4, then "
                "elastography)."},
    {"from": "kidney", "to": "cardiovascular", "studies": ["ckdpc-2010", "prevent-2024", "ckm-2023"],
     "measure": "HR, all-cause mortality at eGFR 45 vs 95", "estimate": 1.57, "ciLow": None, "ciHigh": None,
     "summary": "Below an eGFR of 60, and with any albumin in the urine, the risk of dying, also of heart "
                "disease, rises; the AHA PREVENT equations therefore use eGFR."},
    {"from": "kidney", "to": "bone", "studies": ["kdigo-2017-mbd"],
     "measure": None, "estimate": None, "ciLow": None, "ciHigh": None,
     "summary": "From CKD stage 3a the mineral and bone disorder of CKD raises the fracture risk; the guideline "
                "suggests bone density tests when they would change treatment."},
    {"from": "diabetes", "to": "bone", "studies": ["vestergaard-2007"],
     "measure": "RR, hip fracture", "estimate": 1.38, "ciLow": 1.25, "ciHigh": 1.53,
     "summary": "Type 2 diabetes goes with more hip fractures, although bone density is often higher."},
    {"from": "fitness", "to": "cardiovascular", "studies": ["kodama-2009"],
     "measure": "RR per 1 MET higher fitness, CHD/CVD events", "estimate": 0.85, "ciLow": 0.82, "ciHigh": 0.88,
     "summary": "Each 1 MET more fitness goes with about 15% fewer heart events; low fitness with about 56% more "
                "than high fitness."},
]


def reference_ranges() -> list[dict]:
    return json.loads((HERE / "reference_ranges.json").read_text(encoding="utf-8"))["ranges"]


def _range_rows() -> list[dict]:
    rows = []
    for r in reference_ranges():
        if not r.get("loinc"):
            continue
        rows.append({
            # The edition is part of the key: a superseded range stays next to its successor.
            "id": f"{r['analyteKey']}|{r['ucum']}|{r['sex']}|{r.get('validFrom') or ''}", "loinc": r["loinc"],
            "analyteKey": r["analyteKey"], "ucum": r["ucum"], "sex": r["sex"], "group": r["group"],
            "guidelineLow": r.get("guidelineLow"), "guidelineHigh": r.get("guidelineHigh"),
            "optimalLow": r.get("optimalLow"), "optimalHigh": r.get("optimalHigh"),
            "basis": r["basis"], "summary": r["summary"],
            "sourceLabel": r["source"]["label"], "sourceUrl": r["source"]["url"],
            "sourceYear": r["source"].get("year"), "sourcePmid": r["source"].get("pmid"),
            "sourceDoi": r["source"].get("doi"),
            "validFrom": r.get("validFrom"), "validUntil": r.get("validUntil"),
            "supersededBy": r.get("supersededBy"),
        })
    return rows


def _range_source_rows() -> list[dict]:
    """The source of every range as a Study node: the same kind of evidence node as the risk links use."""
    sources: dict[str, dict] = {}
    for r in _range_rows():
        sid = f"pmid-{r['sourcePmid']}" if r["sourcePmid"] else "src-" + hashlib.sha1(
            r["sourceLabel"].encode()).hexdigest()[:10]
        st = sources.setdefault(sid, {
            "id": sid, "citation": r["sourceLabel"], "title": r["sourceLabel"], "year": r["sourceYear"],
            "design": set(), "url": f"https://doi.org/{r['sourceDoi']}" if r["sourceDoi"] else r["sourceUrl"],
            "pmid": r["sourcePmid"],
            "pubmedUrl": f"https://pubmed.ncbi.nlm.nih.gov/{r['sourcePmid']}/" if r["sourcePmid"] else None,
            "ranges": []})
        st["design"].add(r["basis"])
        st["ranges"].append(r["id"])
    return [st | {"design": "reference range source: " + ", ".join(sorted(st["design"]))} for st in sources.values()]


def _study_rows() -> list[dict]:
    return [{k: v for k, v in st.items() if k not in ("examines", "informs")} |
            {"pubmedUrl": f"https://pubmed.ncbi.nlm.nih.gov/{st['pmid']}/"} for st in STUDIES]


def _examines_rows() -> list[dict]:
    return [{"study": st["id"], "code": code, "name": CODE_NAMES.get(code)}
            for st in STUDIES for code in dict.fromkeys(st["examines"])]


def _informs_rows() -> list[dict]:
    return [{"study": st["id"], "score": score} for st in STUDIES for score in st["informs"]]


def _marker_rows() -> list[dict]:
    return [{"loinc": code, "risk": risk, "source": source} for codes, risk, source in MARKERS for code in codes]


def fingerprint() -> str:
    """Changes whenever any seeded fact changes, so seeding runs only then."""
    blob = json.dumps([HEALTH_RISKS, RISK_SCORES, _marker_rows(), _range_rows(), STUDIES, RISK_LINKS, CODE_NAMES],
                      sort_keys=True)
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

SEED_STUDIES = """
UNWIND $studies AS s
MERGE (st:Study {id: s.id})
SET st.citation = s.citation, st.title = s.title, st.year = s.year, st.design = s.design, st.url = s.url,
    st.pmid = s.pmid, st.pubmedUrl = s.pubmedUrl
RETURN count(st) AS studies
"""

SEED_STUDY_MARKERS = """
UNWIND $examines AS e
MATCH (st:Study {id: e.study})
MERGE (lc:LoincCode {code: e.code})
SET lc.display = coalesce(lc.display, e.name)
MERGE (st)-[k:EXAMINES]->(lc)
RETURN count(k) AS studyMarkers
"""

SEED_STUDY_SCORES = """
UNWIND $informs AS i
MATCH (st:Study {id: i.study})
MATCH (rs:RiskScore {id: i.score})
MERGE (st)-[k:INFORMS]->(rs)
RETURN count(k) AS studyScores
"""

SEED_RISK_LINKS = """
UNWIND $links AS l
MATCH (a:HealthRisk {id: l.from})
MATCH (b:HealthRisk {id: l.to})
MERGE (a)-[k:RAISES_RISK_OF]->(b)
SET k.summary = l.summary, k.measure = l.measure, k.estimate = l.estimate,
    k.ciLow = l.ciLow, k.ciHigh = l.ciHigh, k.studies = l.studies
WITH a, b, k, l
UNWIND l.studies AS sid
MATCH (st:Study {id: sid})
MERGE (st)-[:ABOUT]->(a)
MERGE (st)-[:ABOUT]->(b)
RETURN count(DISTINCT k) AS riskLinks
"""

# A range id the table no longer has (an older key, a removed range) goes, with its links.
SEED_PRUNE_RANGES = """
MATCH (rr:ReferenceRange)
WHERE NOT rr.id IN $rangeIds
DETACH DELETE rr
RETURN count(*) AS prunedRanges
"""

SEED_RANGE_SOURCES = """
UNWIND $rangeSources AS s
MERGE (st:Study {id: s.id})
SET st.citation = s.citation, st.title = s.title, st.year = s.year, st.design = s.design, st.url = s.url,
    st.pmid = s.pmid, st.pubmedUrl = s.pubmedUrl
WITH st, s
UNWIND s.ranges AS rid
MATCH (rr:ReferenceRange {id: rid})
MERGE (rr)-[:SOURCED_FROM]->(st)
RETURN count(DISTINCT st) AS rangeSources
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
        counts.update(dict(conn.execute(SEED_PRUNE_RANGES, {"rangeIds": [r["id"] for r in _range_rows()]}).single()))
        counts.update(dict(conn.execute(SEED_RANGES, {"ranges": _range_rows()}).single()))
        counts.update(dict(conn.execute(SEED_RANGE_SOURCES, {"rangeSources": _range_source_rows()}).single()))
        counts.update(dict(conn.execute(SEED_STUDIES, {"studies": _study_rows()}).single()))
        counts.update(dict(conn.execute(SEED_STUDY_MARKERS, {"examines": _examines_rows()}).single()))
        counts.update(dict(conn.execute(SEED_STUDY_SCORES, {"informs": _informs_rows()}).single()))
        counts.update(dict(conn.execute(SEED_RISK_LINKS, {"links": RISK_LINKS}).single()))
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
