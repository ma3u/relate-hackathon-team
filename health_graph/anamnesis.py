"""Anamnesis from the person's own data: ask only what the graph cannot answer.

A fixed questionnaire asks everyone everything, including what the graph already
knows (a 24-hour blood pressure measurement, Apple Watch exercise minutes, a weight
series, a bone density scan). This module starts from the data instead:

1. **Findings.** The newest value of each analyte (across its LOINC codes and
   units) is compared with the guideline range that applied on its date, in the
   same unit and for the person's sex, else with the range the lab printed. A value
   outside it, or within 5 % of a limit, is a finding; so are FIB-4 at or above
   1.30, a peak systolic pressure in an exercise test at or above 210 mmHg (men)
   or 190 mmHg (women), blood oxygen weeks below 95 %, and a risk score input
   only the person can give (smoking). A value older than 18 months is not
   judged: it goes on the recheck list.
2. **Known.** What the graph already answers: blood pressure measured over 24
   hours or twice in a year, Apple Watch activity, a weight series, a bone density
   scan, and every question answered in the last 12 months.
3. **Questions.** Each rule names the questions its finding raises (why the
   value may be what it is, what it means for the risk); a question the graph
   already answers is skipped, with the reason.

Answers are stored as FHIR-like responses, linked to the risks and to the codes
of the finding that raised them:

  (:Questionnaire)-[:HAS_ITEM]->(:QuestionnaireItem)-[:INFORMS]->(:HealthRisk)
  (:Patient)-[:HAS_RESPONSE]->(:QuestionnaireResponse)-[:RESPONDS_TO]->(:Questionnaire)
  (:QuestionnaireResponse)-[:HAS_ANSWER]->(:Answer {finding})-[:ANSWERS]->(:QuestionnaireItem)
  (:Answer)-[:RISK_FACTOR_FOR]->(:HealthRisk)     only for an answer that is a known risk factor
  (:Answer)-[:BASED_ON]->(:LoincCode)             the measurements the question was asked about

The rules, questions and Cypher are generic and generated into the Swift
library (KnowledgeData.swift, Cypher.swift), so Klarbefund for Mac's MCP server
asks the same questions. The answers belong to one person and go only into their
own store, never into this repository.
"""
from __future__ import annotations

import datetime as dt
import math

QUESTIONNAIRE = {
    "id": "klarbefund-anamnesis",
    "version": "2026-11-15",
    "title": "Anamnesis from my own data",
}

OLD_DAYS = 548        # 18 months: older values go on the recheck list, they are not judged
ANSWER_DAYS = 365     # an answer older than this is asked again
NEAR = 0.05           # within 5 % of a limit, inside it: "at the limit"

# Analytes: one id, its LOINC codes (any unit). The newest value across the codes counts.
GROUPS = [
    {"id": "ldl", "name": "LDL cholesterol", "codes": ["22748-8", "13457-7", "18262-6", "2089-1"]},
    {"id": "apob", "name": "ApoB", "codes": ["1884-6"]},
    {"id": "non-hdl", "name": "Non-HDL cholesterol", "codes": ["70204-3", "43396-1"]},
    {"id": "total-chol", "name": "Total cholesterol", "codes": ["14647-2", "2093-3"]},
    {"id": "lpa", "name": "Lp(a)", "codes": ["10835-7", "43583-4"]},
    {"id": "tg", "name": "Triglycerides", "codes": ["14927-8", "2571-8"]},
    {"id": "ntprobnp", "name": "NT-proBNP", "codes": ["33762-6", "71425-3"]},
    {"id": "hba1c", "name": "HbA1c", "codes": ["4548-4", "17856-6"]},
    {"id": "glucose", "name": "Fasting glucose", "codes": ["1558-6", "2345-7"]},
    {"id": "alt", "name": "ALT", "codes": ["1742-6"]},
    {"id": "ast", "name": "AST", "codes": ["1920-8"]},
    {"id": "ggt", "name": "GGT", "codes": ["2324-2"]},
    {"id": "creatinine", "name": "Creatinine", "codes": ["2160-0"]},
    {"id": "egfr", "name": "eGFR (lab)", "codes": ["62238-1", "98979-8", "33914-3", "48642-3"]},
    {"id": "uacr", "name": "Urine albumin/creatinine", "codes": ["9318-7", "14959-1"]},
    {"id": "crp", "name": "hs-CRP", "codes": ["30522-7"]},
    {"id": "ferritin", "name": "Ferritin", "codes": ["2276-4"]},
    {"id": "tsh", "name": "TSH", "codes": ["3016-3"]},
    {"id": "vitd", "name": "Vitamin D", "codes": ["62292-8", "68438-1", "1989-3"]},
]
GROUP = {g["id"]: g for g in GROUPS}

# The question bank. linkId, text ({date} = the finding's newest date), risks, options
# (code, label, is a risk factor), several answers allowed, and the fact that answers it.
ITEMS = [
    {"linkId": "family-cvd",
     "text": "Did a parent or sibling have a heart attack, stroke or bypass/stent early "
             "(men before 55, women before 65)?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("yes", "Yes", True), ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "family-lipids",
     "text": "Is high cholesterol or high Lp(a) known in your family (familial hypercholesterolaemia)?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("yes", "Yes", True), ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "relatives-lpa",
     "text": "Has anyone in your close family (parents, siblings, children) had Lp(a) measured?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("high", "Yes, it was high", True), ("normal", "Yes, it was normal", False),
                 ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "smoking",
     "text": "Do you smoke, or did you?",
     "risks": ["cardiovascular", "kidney", "bone", "diabetes"], "multiple": False,
     "options": [("never", "Never", False), ("former", "Former smoker", False),
                 ("current", "Current smoker", True)]},
    {"linkId": "blood-pressure",
     "text": "Has a doctor ever told you that your blood pressure is high?",
     "risks": ["cardiovascular", "kidney"], "multiple": False, "knownBy": "bp_measured",
     "options": [("no", "No", False), ("treated", "Yes, and I take medication", True),
                 ("untreated", "Yes, not treated", True), ("unknown", "Never measured / not sure", False)]},
    {"linkId": "home-bp",
     "text": "Do you measure your blood pressure at home, and what do you usually see?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("no", "I don't measure it", False), ("normal", "Yes, usually below 135/85", False),
                 ("higher", "Yes, often 135/85 or higher", True)]},
    {"linkId": "family-hypertension",
     "text": "Does a parent or sibling have high blood pressure?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("yes", "Yes", True), ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "lipid-medication",
     "text": "Do you take, or did you take, medication to lower cholesterol?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("none", "Never", False), ("statin", "A statin", False),
                 ("combination", "Statin plus ezetimibe or another drug", False),
                 ("stopped", "I took one and stopped", False)]},
    {"linkId": "diet-fat",
     "text": "How often do you eat fatty meat, sausage, butter, cheese or pastries?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("daily", "Every day", True), ("weekly", "A few times a week", False),
                 ("rarely", "Rarely", False)]},
    {"linkId": "sample-fasting",
     "text": "Was the blood sample on {date} taken fasting (nothing but water for 8 hours or more)?",
     "risks": ["cardiovascular", "diabetes"], "multiple": False,
     "options": [("yes", "Yes, fasting", False), ("no", "No, I had eaten", False), ("unknown", "Not sure", False)]},
    {"linkId": "exercise-before-sample",
     "text": "Did you do hard endurance exercise or HIIT in the 48 hours before the blood sample on {date}?",
     "risks": ["cardiovascular", "kidney"], "multiple": False,
     "options": [("yes", "Yes", False), ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "cardiac-symptoms",
     "text": "Do you notice any of these?",
     "risks": ["cardiovascular", "fitness"], "multiple": True,
     "options": [("none", "None of these", False),
                 ("chest-pain", "Chest pressure or pain on exertion", True),
                 ("breathless", "Short of breath on stairs or lying flat", True),
                 ("ankle-swelling", "Swollen ankles in the evening", True),
                 ("palpitations", "Racing or irregular heartbeat", True)]},
    {"linkId": "alcohol",
     "text": "How many alcoholic drinks do you have in a typical week (one drink = a small beer or glass of wine)?",
     "risks": ["liver", "cardiovascular", "bone"], "multiple": False,
     "options": [("none", "None", False), ("1-7", "1 to 7", False),
                 ("8-14", "8 to 14", True), ("15+", "15 or more", True)]},
    {"linkId": "sugary-drinks",
     "text": "How often do you have sweets, sugary drinks or juice?",
     "risks": ["diabetes", "liver"], "multiple": False,
     "options": [("daily", "Every day", True), ("weekly", "A few times a week", False),
                 ("rarely", "Rarely", False)]},
    {"linkId": "liver-imaging",
     "text": "Has your liver ever been examined by ultrasound or elastography (FibroScan)?",
     "risks": ["liver"], "multiple": False,
     "options": [("never", "Never", False), ("normal", "Yes, it was normal", False),
                 ("fatty", "Yes, fatty liver was seen", True),
                 ("elastography", "Yes, with elastography (stiffness measured)", False)]},
    {"linkId": "supplements-meds",
     "text": "Which medication and supplements do you take regularly (including herbal ones)?",
     "risks": ["liver", "kidney"], "multiple": False,
     "options": [("none", "None", False), ("some", "Some (please name them)", False)]},
    {"linkId": "family-diabetes",
     "text": "Does a parent or sibling have type 2 diabetes?",
     "risks": ["diabetes"], "multiple": False,
     "options": [("yes", "Yes", True), ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "weight-change",
     "text": "How has your weight changed over the last two years?",
     "risks": ["diabetes", "liver", "cardiovascular"], "multiple": False, "knownBy": "weight_series",
     "options": [("stable", "Stable", False), ("gained", "Gained more than 5 kg", True),
                 ("lost-planned", "Lost weight on purpose", False),
                 ("lost-unplanned", "Lost weight without trying", False)]},
    {"linkId": "exercise",
     "text": "How much exercise that makes you breathe harder do you get in a typical week?",
     "risks": ["fitness", "cardiovascular", "diabetes"], "multiple": False, "knownBy": "activity_measured",
     "options": [("<1h", "Less than 1 hour", True), ("1-2.5h", "1 to 2.5 hours", False),
                 ("2.5-5h", "2.5 to 5 hours", False), ("5h+", "More than 5 hours", False)]},
    {"linkId": "painkillers",
     "text": "How often do you take painkillers such as ibuprofen, diclofenac or naproxen?",
     "risks": ["kidney"], "multiple": False,
     "options": [("rarely", "Rarely or never", False), ("monthly", "A few times a month", False),
                 ("weekly", "Every week", True), ("daily", "Almost every day", True)]},
    {"linkId": "creatine-protein",
     "text": "Do you take creatine, or eat a lot of protein (shakes, more than about 1.6 g per kg a day)?",
     "risks": ["kidney"], "multiple": False,
     "options": [("creatine", "Creatine", False), ("protein", "A lot of protein", False),
                 ("both", "Both", False), ("neither", "Neither", False)]},
    {"linkId": "fracture",
     "text": "Have you broken a bone after age 40 from a minor fall, or lost height?",
     "risks": ["bone"], "multiple": False, "knownBy": "bone_density",
     "options": [("no", "No", False), ("fracture", "Yes, a fracture", True),
                 ("height", "Yes, lost height", True)]},
    {"linkId": "supplements",
     "text": "Do you take vitamin D or calcium?",
     "risks": ["bone"], "multiple": False,
     "options": [("none", "No", False), ("vitamin-d", "Vitamin D", False),
                 ("vitamin-d-calcium", "Vitamin D and calcium", False)]},  # any other supplement goes in text
    {"linkId": "sleep-apnoea",
     "text": "Do you snore loudly, or has someone seen you stop breathing in your sleep?",
     "risks": ["cardiovascular", "diabetes"], "multiple": False,
     "options": [("no", "No", False), ("snoring", "Loud snoring", True),
                 ("pauses", "Breathing pauses were seen", True), ("diagnosed", "Sleep apnoea diagnosed", True)]},
    {"linkId": "sleep-apnoea-treatment",
     "text": "If you were diagnosed with sleep apnoea: is it treated now?",
     "risks": ["cardiovascular", "diabetes"], "multiple": False,
     "options": [("none", "No treatment", False), ("cpap", "CPAP", False),
                 ("splint", "Oral splint", False), ("stopped", "Treatment stopped", False)]},
]
ITEM = {i["linkId"]: i for i in ITEMS}

# What a finding is, why it matters, and the questions it raises. "groups" + "when"
# trigger on analyte values; "kind" on the special findings (fib4, exercise_bp,
# spo2, missing_answer). "tests": suggestions for the doctor; "ifMissing": a test
# suggested when that analyte has no value at all.
RULES = [
    {"id": "lipids", "title": "LDL cholesterol or ApoB above the guideline",
     "groups": ["ldl", "apob", "non-hdl", "total-chol"], "when": ["high"], "risks": ["cardiovascular"],
     "why": "LDL cholesterol causes atherosclerosis and ApoB counts its particles; how far to lower them "
            "depends on the whole risk (ESC/EAS 2019 and the 2025 focused update).",
     "questions": ["lipid-medication", "diet-fat", "family-lipids", "family-cvd"],
     "ifMissing": {"apob": "ApoB, the better single measure when triglycerides are high (ESC/EAS 2019)",
                   "lpa": "Lp(a), once in every adult's life (ESC/EAS 2025)"}},
    {"id": "lpa", "title": "Lp(a) raised or above the lab's limit",
     "groups": ["lpa"], "when": ["high", "at_limit", "lab_high"], "risks": ["cardiovascular"],
     "why": "Lp(a) is mostly inherited and changes little over life; raised Lp(a) adds to the risk from "
            "LDL, and close relatives should be tested (ESC/EAS 2025; EAS consensus 2022).",
     "questions": ["family-cvd", "family-lipids", "relatives-lpa"]},
    {"id": "triglycerides", "title": "Triglycerides above the guideline",
     "groups": ["tg"], "when": ["high", "at_limit"], "risks": ["cardiovascular", "diabetes", "liver"],
     "why": "Triglycerides rise after a meal, with alcohol and sugar, and with insulin resistance.",
     "questions": ["sample-fasting", "alcohol", "sugary-drinks"]},
    {"id": "ntprobnp", "title": "NT-proBNP at or above the limit",
     "groups": ["ntprobnp"], "when": ["high", "at_limit", "lab_high"], "risks": ["cardiovascular"],
     "why": "NT-proBNP rises when the heart is under strain, but also for a day or two after hard endurance "
            "exercise and when the kidneys filter less; below 125 ng/L makes heart failure unlikely (ESC 2021).",
     "questions": ["cardiac-symptoms", "exercise-before-sample"],
     "tests": ["An echocardiogram if there are symptoms (ESC 2021 heart failure guideline)"]},
    {"id": "glucose", "title": "Blood sugar at or above the limit",
     "groups": ["hba1c", "glucose"], "when": ["high", "at_limit"], "risks": ["diabetes"],
     "why": "HbA1c from 5.7 % or fasting glucose from 100 mg/dL is prediabetes (ADA 2025).",
     "questions": ["family-diabetes", "sugary-drinks", "sample-fasting", "sleep-apnoea"]},
    {"id": "liver_enzymes", "title": "Liver enzymes above the guideline",
     "groups": ["alt", "ast", "ggt"], "when": ["high"], "risks": ["liver"],
     "why": "Raised liver enzymes point to fat, alcohol, medication or supplements stressing the liver.",
     "questions": ["alcohol", "liver-imaging", "supplements-meds"]},
    {"id": "fib4", "title": "FIB-4 between the cut-offs or above", "kind": "fib4", "risks": ["liver"],
     "why": "FIB-4 from 1.30 cannot rule out liver fibrosis; EASL 2024 then advises a second test, "
            "elastography or the ELF blood test.",
     "questions": ["alcohol", "liver-imaging", "supplements-meds"],
     "tests": ["Liver elastography (FibroScan) or the ELF blood test (EASL-EASD-EASO 2024)"]},
    {"id": "kidney", "title": "Creatinine above the guideline or eGFR below 60",
     "groups": ["creatinine", "egfr"], "when": ["high", "low"], "risks": ["kidney"],
     "why": "Creatinine also rises with muscle mass, creatine, a high-protein diet and hard exercise "
            "before the sample; CKD needs a finding that lasts three months (KDIGO 2024).",
     "questions": ["painkillers", "creatine-protein", "exercise-before-sample"],
     "tests": ["Cystatin C, when creatinine may mislead (KDIGO 2024)"],
     "ifMissing": {"uacr": "Urine albumin-to-creatinine ratio: KDIGO stages kidney disease by eGFR and albumin"}},
    {"id": "vitamin_d", "title": "Vitamin D below the range", "groups": ["vitd"], "when": ["low"],
     "risks": ["bone"],
     "why": "The 30 ng/mL threshold is the Endocrine Society's 2011 range; its 2024 guideline sets no target.",
     "questions": ["supplements"]},
    {"id": "exercise_bp", "title": "High blood pressure at peak exercise", "kind": "exercise_bp",
     "risks": ["cardiovascular"],
     "why": "A peak systolic pressure from 210 mmHg (men) or 190 mmHg (women) in an exercise test is an "
            "exaggerated response; in studies it goes with later high blood pressure at rest.",
     "questions": ["family-hypertension", "home-bp"]},
    {"id": "oxygen", "title": "Blood oxygen weeks below 95 %", "kind": "spo2",
     "risks": ["cardiovascular", "diabetes"],
     "why": "Low night-time oxygen on the watch can be a sign of sleep apnoea, which raises blood pressure "
            "and heart risk.",
     "questions": ["sleep-apnoea", "sleep-apnoea-treatment"]},
    {"id": "smoking_unknown", "title": "SCORE2 needs your smoking status", "kind": "missing_answer",
     "answer": "smoking", "risks": ["cardiovascular"],
     "why": "SCORE2, the 10-year heart and stroke risk, counts any current smoking; the graph cannot know it.",
     "questions": ["smoking"]},
]
RULE = {r["id"]: r for r in RULES}

# ── the finder's queries (generated into the Swift library as well) ──────────

# The newest value of each analyte, with the guideline range valid on its date in
# the same unit and for the person's sex, and the lab's printed range.
FINDINGS = """
MATCH (p:Patient)
UNWIND $groups AS g
MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(c:LoincCode)
WHERE c.code IN g.codes AND o.duplicateOf IS NULL AND o.valueQuantity IS NOT NULL
  AND coalesce(o.sourceKind, '') <> 'device-weekly-mean'
WITH p, g, o ORDER BY o.effectiveDate DESC
WITH p, g, collect(o)[0] AS o
MATCH (o)-[:CODED_BY]->(c:LoincCode)
OPTIONAL MATCH (r:ReferenceRange)-[:APPLIES_TO]->(c)
WHERE toLower(r.ucum) = toLower(o.unit) AND r.sex IN ['any', coalesce(p.gender, 'any')]
  AND coalesce(r.validFrom, '0000') <= o.effectiveDate
  AND (r.validUntil IS NULL OR o.effectiveDate < r.validUntil)
WITH g, o, c, collect(r)[0] AS r
RETURN g.id AS group, c.code AS code, o.display AS display, o.valueQuantity AS value, o.unit AS unit,
       o.effectiveDate AS date, o.comparator AS comparator,
       r.guidelineLow AS low, r.guidelineHigh AS high, r.sourceLabel AS source,
       o.referenceLow AS labLow, o.referenceHigh AS labHigh
"""

# What the graph already answers.
FACTS = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(abpm:Observation)-[:CODED_BY]->(ac:LoincCode)
WHERE ac.code IN ['8490-5', '8472-3', '96608-5', '96609-3'] AND abpm.effectiveDate >= $since3y
WITH p, max(abpm.effectiveDate) AS abpm
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(bp:Observation)-[:CODED_BY]->(:LoincCode {code: '8480-6'})
WHERE bp.effectiveDate >= $since1y AND bp.duplicateOf IS NULL
WITH p, abpm, count(bp) AS officeBp, max(bp.effectiveDate) AS lastBp
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(ex:Observation)-[:CODED_BY]->(:LoincCode {code: '55411-3'})
WHERE ex.sourceKind = 'device-weekly-mean' AND ex.effectiveDate >= $since1y
WITH p, abpm, officeBp, lastBp, count(ex) AS activeWeeks
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(w:Observation)-[:CODED_BY]->(:LoincCode {code: '29463-7'})
WHERE w.effectiveDate >= $since3y AND w.duplicateOf IS NULL
WITH p, abpm, officeBp, lastBp, activeWeeks, count(w) AS weights, min(w.effectiveDate) AS firstWeight,
     max(w.effectiveDate) AS lastWeight
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(d:Observation)
WHERE d.duplicateOf IS NULL AND (toLower(coalesce(d.display, '')) CONTAINS 'knochendichte'
   OR toLower(coalesce(d.display, '')) CONTAINS 'bone mineral density'
   OR d.code IN ['38263-0', '38262-2', '46278-8', '80948-3'])
RETURN abpm, officeBp, lastBp, activeWeeks, weights, firstWeight, lastWeight,
       max(d.effectiveDate) AS boneDensity, p.birthYear AS birthYear, p.gender AS sex
"""

# The questions answered before, newest answer per question.
ANSWERED = """
MATCH (:Patient)-[:HAS_RESPONSE]->(:QuestionnaireResponse)-[:HAS_ANSWER]->(a:Answer)
WITH a.linkId + CASE WHEN a.context IS NULL THEN '' ELSE '@' + a.context END AS key, a
ORDER BY a.authored DESC
WITH key, collect(a)[0] AS a
RETURN key, a.authored AS authored, a.labels AS labels, a.text AS text
"""

# FIB-4 inputs: the newest day with AST and ALT (U/L; ukat/L is converted), the age then,
# and every platelet count; the code takes the one nearest that day, within 14 days.
FIB4 = """
MATCH (p:Patient)-[:HAS_OBSERVATION]->(a:Observation)-[:CODED_BY]->(:LoincCode {code: '1920-8'})
WHERE a.duplicateOf IS NULL AND p.birthYear IS NOT NULL AND a.valueQuantity > 0
MATCH (p)-[:HAS_OBSERVATION]->(l:Observation)-[:CODED_BY]->(:LoincCode {code: '1742-6'})
WHERE l.duplicateOf IS NULL AND l.effectiveDate = a.effectiveDate AND l.valueQuantity > 0
WITH p, a, l ORDER BY a.effectiveDate DESC
WITH p, collect([a, l])[0] AS day
WITH p, day[0] AS a, day[1] AS l
OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(t:Observation)-[:CODED_BY]->(tc:LoincCode)
WHERE tc.code IN ['777-3', '26515-7'] AND t.duplicateOf IS NULL AND t.valueQuantity > 0
RETURN a.effectiveDate AS date, toInteger(substring(a.effectiveDate, 0, 4)) - p.birthYear AS age,
       a.valueQuantity AS ast, a.unit AS astUnit, l.valueQuantity AS alt, l.unit AS altUnit,
       collect([t.effectiveDate, t.valueQuantity]) AS platelets
"""

# A FIB-4 the scores command stored (the command-line route computes it there).
STORED_FIB4 = """
MATCH (:Patient)-[:HAS_SCORE]->(s:ScoreResult)-[:OF]->(:RiskScore {id: 'fib4'})
RETURN s.value AS value, s.computedAt AS computedAt, s.band AS band
"""

# The highest peak systolic pressure of the newest exercise test.
EXERCISE_BP = """
MATCH (p:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(:LoincCode {code: '87739-9'})
WHERE o.valueQuantity IS NOT NULL
WITH p, o ORDER BY o.effectiveDate DESC, o.valueQuantity DESC
WITH p, collect(o)[0] AS o
RETURN o.effectiveDate AS date, o.valueQuantity AS value, o.unit AS unit, p.gender AS sex
"""

# Apple Watch weeks with mean blood oxygen below 95 % in the last year.
SPO2 = """
MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(:LoincCode {code: '59408-5'})
WHERE o.sourceKind = 'device-weekly-mean' AND o.effectiveDate >= $since1y
RETURN count(o) AS weeks, sum(CASE WHEN o.valueQuantity < 95 THEN 1 ELSE 0 END) AS low,
       min(o.valueQuantity) AS lowest
"""


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days


def _flag(value: float, low, high) -> str:
    if high is not None and value > high:
        return "high"
    if low is not None and value < low:
        return "low"
    if high is not None and high > 0 and value >= high * (1 - NEAR):
        return "at_limit"
    if low is not None and low > 0 and value <= low * (1 + NEAR):
        return "at_limit_low"
    return "ok"


def judge(row: dict, today: str) -> dict:
    """One analyte's newest value, judged against the guideline (else the lab's) range."""
    value = row["value"]
    guideline = row["low"] is not None or row["high"] is not None
    low, high = (row["low"], row["high"]) if guideline else (row["labLow"], row["labHigh"])
    out = {k: row[k] for k in ("group", "code", "display", "value", "unit", "date")}
    out["ageDays"] = _days(row["date"], today)
    out["range"] = {"low": low, "high": high, "basis": "guideline" if guideline else "lab",
                    "source": row["source"] if guideline else "the lab's printed range"}
    out["flag"] = _flag(value, low, high) if (low is not None or high is not None) else "no_range"
    lab = _flag(value, row["labLow"], row["labHigh"]) if guideline else out["flag"]
    out["labFlag"] = lab
    if guideline and lab == "high" and out["flag"] not in ("high", "at_limit"):
        out["flag_lab_only"] = True
    return out


FIB4_DAYS = 14   # platelets this close to the AST/ALT day count as the same visit


def fib4(r: dict) -> dict | None:
    """FIB-4 from the FIB4 row: AST and ALT of one day, the nearest platelet count within 14 days."""
    per = lambda unit: 60.0 if (unit or "").lower().replace("µ", "u") == "ukat/l" else 1.0
    near = [(abs(_days(d, r["date"])), v) for d, v in (r.get("platelets") or []) if d and v]
    near = [x for x in near if x[0] <= FIB4_DAYS]
    if not (r.get("age") and near):
        return None
    ast, alt = r["ast"] * per(r["astUnit"]), r["alt"] * per(r["altUnit"])
    platelets = min(near)[1]
    return {"value": round(r["age"] * ast / (platelets * math.sqrt(alt)), 2), "date": r["date"],
            "age": r["age"], "ast": round(ast, 1), "alt": round(alt, 1), "platelets": platelets}


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _one(conn, cypher: str, params: dict | None = None) -> dict | None:
    for r in conn.execute(cypher, params or {}):
        return dict(r)
    return None


def plan(conn, today: str | None = None) -> dict:
    """Findings in the person's data, what the graph already answers, and the questions to ask."""
    today = today or dt.date.today().isoformat()
    t = dt.date.fromisoformat(today)
    since1y, since3y = _iso(t - dt.timedelta(days=365)), _iso(t - dt.timedelta(days=3 * 365))
    rows = [dict(r) for r in conn.execute(FINDINGS, {"groups": [{"id": g["id"], "codes": g["codes"]}
                                                                for g in GROUPS]})]
    values = {r["group"]: judge(r, today) for r in rows}
    facts_row = _one(conn, FACTS, {"since1y": since1y, "since3y": since3y}) or {}
    answered = {r["key"]: dict(r) for r in conn.execute(ANSWERED)}

    known: dict[str, str] = {}
    if facts_row.get("abpm"):
        known["bp_measured"] = f"24-hour blood pressure measurement on {facts_row['abpm']}"
    elif (facts_row.get("officeBp") or 0) >= 2:
        known["bp_measured"] = f"{facts_row['officeBp']} blood pressure readings in the last year"
    if (facts_row.get("activeWeeks") or 0) >= 8:
        known["activity_measured"] = f"Apple Watch exercise minutes for {facts_row['activeWeeks']} weeks of the last year"
    if (facts_row.get("weights") or 0) >= 3:
        known["weight_series"] = (f"{facts_row['weights']} weights from {facts_row['firstWeight']} "
                                  f"to {facts_row['lastWeight']}")
    if facts_row.get("boneDensity"):
        known["bone_density"] = f"bone density scan on {facts_row['boneDensity']}"
    recent = {k: a for k, a in answered.items() if a["authored"] and _days(a["authored"], today) <= ANSWER_DAYS}

    findings, rechecks = [], []
    for g in GROUPS:
        v = values.get(g["id"])
        if v and v["ageDays"] > OLD_DAYS and v["flag"] not in ("ok", "no_range"):
            rechecks.append({**v, "name": g["name"]})
    for rule in RULES:
        hits: list[dict] = []
        detail = None
        kind = rule.get("kind")
        if kind is None:
            for gid in rule["groups"]:
                v = values.get(gid)
                if not v or v["ageDays"] > OLD_DAYS:
                    continue
                flag = "lab_high" if v.get("flag_lab_only") else v["flag"]
                if flag == "at_limit_low":
                    flag = "low" if "low" in rule["when"] else flag
                if flag in rule["when"] or (flag == "lab_high" and "lab_high" in rule["when"]):
                    hits.append({**v, "name": GROUP[gid]["name"], "trigger": flag})
        elif kind == "fib4":
            r = _one(conn, FIB4)
            computed = fib4(r) if r else None
            if computed is None:
                s = _one(conn, STORED_FIB4)
                if s and s["value"] is not None:
                    computed = {"value": round(s["value"], 2), "date": (s["computedAt"] or "")[:10],
                                "stored": True, "band": s["band"]}
            if computed and computed["value"] >= 1.30 and _days(computed["date"], today) <= OLD_DAYS:
                detail = {**computed, "cutOffs": "below 1.30 rules fibrosis out, 2.67 and above rules it in "
                                                 "(EASL; 2.0 instead of 1.30 from age 65)"}
                hits = [{"code": c} for c in ("1920-8", "1742-6", "777-3")]
        elif kind == "exercise_bp":
            r = _one(conn, EXERCISE_BP)
            if r and r["value"] is not None:
                limit = 190 if (r["sex"] or "").lower() == "female" else 210
                if r["value"] >= limit and _days(r["date"], today) <= 3 * 365:
                    detail = {"value": r["value"], "unit": r["unit"], "date": r["date"], "limit": limit}
                    hits = [{"code": "87739-9"}]
        elif kind == "spo2":
            r = _one(conn, SPO2, {"since1y": since1y})
            if r and (r["low"] or 0) >= 2:
                detail = {"lowWeeks": r["low"], "weeks": r["weeks"], "lowest": r["lowest"]}
                hits = [{"code": "59408-5"}]
        elif kind == "missing_answer":
            if rule["answer"] not in recent:
                detail = {"missing": rule["answer"]}
        if not hits and detail is None:
            continue
        missing = [{"group": gid, "test": text} for gid, text in rule.get("ifMissing", {}).items()
                   if gid not in values]
        findings.append({"id": rule["id"], "title": rule["title"], "why": rule["why"], "risks": rule["risks"],
                         "values": [h for h in hits if "group" in h], "detail": detail,
                         "codes": sorted({h["code"] for h in hits}),
                         "date": max((h.get("date") or "" for h in hits), default="") or (detail or {}).get("date"),
                         "tests": rule.get("tests", []) + [m["test"] for m in missing]})

    questions, skipped, seen = [], [], set()
    for f in findings:
        for link_id in RULE[f["id"]]["questions"]:
            item = ITEM[link_id]
            dated = "{date}" in item["text"]
            key = f"{link_id}@{f['date']}" if dated and f["date"] else link_id
            if key in seen:
                for q in questions:
                    if q["key"] == key and f["id"] not in q["findings"]:
                        q["findings"].append(f["id"])
                        q["basedOn"] = sorted(set(q["basedOn"]) | set(f["codes"]))
                continue
            seen.add(key)
            if key in recent:
                a = recent[key]
                skipped.append({"key": key, "linkId": link_id, "finding": f["id"],
                                "reason": f"answered on {a['authored'][:10]}: "
                                          f"{', '.join(a['labels'] or [])}{' / ' + a['text'] if a['text'] else ''}"})
                continue
            if item.get("knownBy") in known:
                skipped.append({"key": key, "linkId": link_id, "finding": f["id"],
                                "reason": known[item["knownBy"]]})
                continue
            questions.append({"key": key, "linkId": link_id, "context": f["date"] if dated else None,
                              "text": item["text"].replace("{date}", f["date"] or "that day"),
                              "options": [{"code": c, "label": lab, "riskFactor": rf}
                                          for c, lab, rf in item["options"]],
                              "multiple": item["multiple"], "risks": item["risks"],
                              "findings": [f["id"]], "basedOn": list(f["codes"])})
    return {"asOf": today, "sex": facts_row.get("sex"), "birthYear": facts_row.get("birthYear"),
            "findings": findings, "known": [{"fact": k, "detail": v} for k, v in known.items()],
            "questions": questions, "skipped": skipped,
            "rechecks": [{"name": r["name"], "display": r["display"], "date": r["date"], "flag": r["flag"],
                          "ageDays": r["ageDays"]} for r in rechecks]}


# ── storing answers ──────────────────────────────────────────────────────────

def _item_rows() -> list[dict]:
    return [{"linkId": i["linkId"], "text": i["text"], "multiple": i["multiple"], "risks": i["risks"],
             "options": [code for code, _, _ in i["options"]],
             "labels": [label for _, label, _ in i["options"]],
             "riskFactors": [code for code, _, factor in i["options"] if factor]}
            for i in ITEMS]


SEED_QUESTIONNAIRE = """
MERGE (q:Questionnaire {id: $id})
SET q.version = $version, q.title = $title
WITH q
UNWIND $items AS it
MERGE (i:QuestionnaireItem {id: $id + '|' + it.linkId})
SET i.linkId = it.linkId, i.text = it.text, i.multiple = it.multiple, i.options = it.options,
    i.labels = it.labels, i.riskFactors = it.riskFactors
MERGE (q)-[:HAS_ITEM]->(i)
WITH i, it
OPTIONAL MATCH (i)-[old:INFORMS]->()
DELETE old
WITH DISTINCT i, it
UNWIND it.risks AS riskId
MATCH (h:HealthRisk {id: riskId})
MERGE (i)-[:INFORMS]->(h)
RETURN count(*) AS links
"""

STORE_RESPONSE = """
MATCH (p:Patient {id: $patientId})
MATCH (q:Questionnaire {id: $questionnaire})
MERGE (r:QuestionnaireResponse {id: $responseId})
SET r.authored = $authored, r.status = 'completed', r.source = $source, r.version = q.version
MERGE (p)-[:HAS_RESPONSE]->(r)
MERGE (r)-[:RESPONDS_TO]->(q)
WITH r
UNWIND $answers AS a
MATCH (i:QuestionnaireItem {id: $questionnaire + '|' + a.linkId})
MERGE (ans:Answer {id: $responseId + '|' + a.key})
SET ans.linkId = a.linkId, ans.context = a.context, ans.question = a.question, ans.codes = a.codes, ans.labels = a.labels,
    ans.text = a.text, ans.riskFactor = a.riskFactor, ans.authored = $authored, ans.findings = a.findings
MERGE (r)-[:HAS_ANSWER]->(ans)
MERGE (ans)-[:ANSWERS]->(i)
WITH ans, a
UNWIND CASE WHEN a.riskFactor THEN a.risks ELSE [] END AS riskId
MATCH (h:HealthRisk {id: riskId})
MERGE (ans)-[:RISK_FACTOR_FOR]->(h)
RETURN count(*) AS links
"""

STORE_BASED_ON = """
UNWIND $rows AS row
MATCH (ans:Answer {id: $responseId + '|' + row.key})
UNWIND row.basedOn AS code
MATCH (c:LoincCode {code: code})
MERGE (ans)-[:BASED_ON]->(c)
RETURN count(*) AS links
"""

# The latest answer per question, for the scores and for Claude.
LATEST_ANSWERS = """
MATCH (:Patient {id: $patientId})-[:HAS_RESPONSE]->(r:QuestionnaireResponse)-[:HAS_ANSWER]->(a:Answer)
WITH a.linkId AS linkId, a ORDER BY a.authored DESC
WITH linkId, collect(a)[0] AS a
RETURN linkId, a.id AS id, a.codes AS codes, a.labels AS labels, a.text AS text, a.riskFactor AS riskFactor
"""

# A score that used an answer (SCORE2 and smoking) points at it, as it points at its lab values.
LINK_SCORE_ANSWER = """
MATCH (sr:ScoreResult {id: $scoreId}), (a:Answer {id: $answerId})
OPTIONAL MATCH (sr)-[old:FROM_ANSWER]->()
DELETE old
WITH DISTINCT sr, a
MERGE (sr)-[:FROM_ANSWER]->(a)
"""


def seed(conn) -> int:
    rec = conn.execute(SEED_QUESTIONNAIRE, {**QUESTIONNAIRE, "items": _item_rows()}).single()
    return rec["links"] if rec else 0


def normalise(answers: dict) -> list[dict]:
    """{linkId: code | [codes] | {"codes", "text", "basedOn": [LOINC], "findings": [rule ids],
    "question": the text as asked}} -> rows for STORE_RESPONSE.

    A code that is not one of the question's options is refused, so a typo can
    never land in the graph as an answer; free text goes into "text".
    """
    rows = []
    for key, value in answers.items():
        link_id, _, context = key.partition("@")
        item = ITEM.get(link_id)
        if item is None:
            raise ValueError(f"unknown question {link_id!r}; known: {', '.join(ITEM)}")
        based_on: list[str] = []
        findings: list[str] = []
        question = item["text"].replace("{date}", context or "that day")
        if isinstance(value, dict):
            codes, text = value.get("codes") or [], value.get("text")
            based_on, findings = value.get("basedOn") or [], value.get("findings") or []
            question = value.get("question") or question
        else:
            codes, text = ([value] if isinstance(value, str) else list(value)), None
        options = {code: (label, factor) for code, label, factor in item["options"]}
        bad = [c for c in codes if c not in options]
        if bad:
            raise ValueError(f"{link_id}: {bad} not among {list(options)}")
        if len(codes) > 1 and not item["multiple"]:
            raise ValueError(f"{link_id} takes one answer, got {codes}")
        unknown = [f for f in findings if f not in RULE]
        if unknown:
            raise ValueError(f"{link_id}: unknown findings {unknown}")
        if not codes and not text:
            continue
        rows.append({"key": key, "linkId": link_id, "context": context or None, "codes": codes, "labels": [options[c][0] for c in codes],
                     "text": text, "riskFactor": any(options[c][1] for c in codes),
                     "risks": item["risks"], "basedOn": based_on, "findings": findings,
                     "question": question})
    return rows


def store_response(conn, patient_id: str, answers: dict, source: str = "chat",
                   authored: str | None = None) -> dict[str, int]:
    authored = authored or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = normalise(answers)
    seed(conn)
    response_id = f"{patient_id}|{QUESTIONNAIRE['id']}|{authored}"
    conn.execute(STORE_RESPONSE, {"patientId": patient_id, "questionnaire": QUESTIONNAIRE["id"],
                                  "responseId": response_id, "authored": authored, "source": source,
                                  "answers": rows})
    rec = conn.execute(STORE_BASED_ON, {"responseId": response_id,
                                        "rows": [r for r in rows if r["basedOn"]]}).single()
    return {"answers": len(rows), "riskFactors": sum(r["riskFactor"] for r in rows),
            "basedOn": rec["links"] if rec else 0}


def latest_answers(conn, patient_id: str) -> dict[str, dict]:
    return {r["linkId"]: dict(r) for r in conn.execute(LATEST_ANSWERS, {"patientId": patient_id})}
