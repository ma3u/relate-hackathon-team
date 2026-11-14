"""Anamnesis: the questions a doctor would ask about the health risks the graph tracks.

Lab values say what the blood shows; they do not say whether a father had a heart
attack at 50, how much someone drinks, or whether stairs make them breathless.
This module holds those questions, each linked to the health risks it informs,
and stores a person's answers in the graph, modelled on FHIR Questionnaire and
QuestionnaireResponse:

  (:Questionnaire)-[:HAS_ITEM]->(:QuestionnaireItem)-[:INFORMS]->(:HealthRisk)
  (:Patient)-[:HAS_RESPONSE]->(:QuestionnaireResponse)-[:RESPONDS_TO]->(:Questionnaire)
  (:QuestionnaireResponse)-[:HAS_ANSWER]->(:Answer)-[:ANSWERS]->(:QuestionnaireItem)
  (:Answer)-[:RISK_FACTOR_FOR]->(:HealthRisk)     only for an answer that is a known risk factor
  (:Answer)-[:BASED_ON]->(:LoincCode)             when the answer was read from measurements in the graph

Every run adds a new response with its own date, so earlier answers stay as history.
The questions are generic; the answers belong to one person and go only into
their own store (the encrypted vault), never into this repository.
"""
from __future__ import annotations

import datetime as dt

QUESTIONNAIRE = {
    "id": "klarbefund-anamnesis",
    "version": "2026-11-14",
    "title": "Anamnesis for the health risks in the graph",
}

# linkId, question, risks it informs, options (code, label, is a risk factor), multiple answers allowed
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
    {"linkId": "smoking",
     "text": "Do you smoke, or did you?",
     "risks": ["cardiovascular", "kidney", "bone", "diabetes"], "multiple": False,
     "options": [("never", "Never", False), ("former", "Former smoker", False),
                 ("current", "Current smoker", True)]},
    {"linkId": "blood-pressure",
     "text": "Has a doctor ever told you that your blood pressure is high?",
     "risks": ["cardiovascular", "kidney"], "multiple": False,
     "options": [("no", "No", False), ("treated", "Yes, and I take medication", True),
                 ("untreated", "Yes, not treated", True), ("unknown", "Never measured / not sure", False)]},
    {"linkId": "lipid-medication",
     "text": "Do you take medication to lower cholesterol?",
     "risks": ["cardiovascular"], "multiple": False,
     "options": [("none", "No", False), ("statin", "A statin", False),
                 ("combination", "Statin plus ezetimibe or another drug", False),
                 ("stopped", "I took one and stopped", False)]},
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
    {"linkId": "liver-imaging",
     "text": "Has your liver ever been examined by ultrasound or elastography (FibroScan)?",
     "risks": ["liver"], "multiple": False,
     "options": [("never", "Never", False), ("normal", "Yes, it was normal", False),
                 ("fatty", "Yes, fatty liver was seen", True),
                 ("elastography", "Yes, with elastography (stiffness measured)", False)]},
    {"linkId": "family-diabetes",
     "text": "Does a parent or sibling have type 2 diabetes?",
     "risks": ["diabetes"], "multiple": False,
     "options": [("yes", "Yes", True), ("no", "No", False), ("unknown", "Not sure", False)]},
    {"linkId": "weight-change",
     "text": "How has your weight changed over the last two years?",
     "risks": ["diabetes", "liver", "cardiovascular"], "multiple": False,
     "options": [("stable", "Stable", False), ("gained", "Gained more than 5 kg", True),
                 ("lost-planned", "Lost weight on purpose", False),
                 ("lost-unplanned", "Lost weight without trying", False)]},
    {"linkId": "exercise",
     "text": "How much exercise that makes you breathe harder do you get in a typical week?",
     "risks": ["fitness", "cardiovascular", "diabetes"], "multiple": False,
     "options": [("<1h", "Less than 1 hour", True), ("1-2.5h", "1 to 2.5 hours", False),
                 ("2.5-5h", "2.5 to 5 hours", False), ("5h+", "More than 5 hours", False)]},
    {"linkId": "painkillers",
     "text": "How often do you take painkillers such as ibuprofen, diclofenac or naproxen?",
     "risks": ["kidney"], "multiple": False,
     "options": [("rarely", "Rarely or never", False), ("monthly", "A few times a month", False),
                 ("weekly", "Every week", True), ("daily", "Almost every day", True)]},
    {"linkId": "fracture",
     "text": "Have you broken a bone after age 40 from a minor fall, or lost height?",
     "risks": ["bone"], "multiple": False,
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
MERGE (ans:Answer {id: $responseId + '|' + a.linkId})
SET ans.linkId = a.linkId, ans.question = i.text, ans.codes = a.codes, ans.labels = a.labels,
    ans.text = a.text, ans.riskFactor = a.riskFactor, ans.authored = $authored
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
MATCH (ans:Answer {id: $responseId + '|' + row.linkId})
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
    """{linkId: code | [codes] | {"codes": [...], "text": "...", "basedOn": [LOINC]}} -> rows.

    A code that is not one of the question's options is refused, so a typo can
    never land in the graph as an answer; free text goes into "text".
    """
    rows = []
    for link_id, value in answers.items():
        item = ITEM.get(link_id)
        if item is None:
            raise ValueError(f"unknown question {link_id!r}; known: {', '.join(ITEM)}")
        based_on: list[str] = []
        if isinstance(value, dict):
            codes, text, based_on = value.get("codes") or [], value.get("text"), value.get("basedOn") or []
        else:
            codes, text = ([value] if isinstance(value, str) else list(value)), None
        options = {code: (label, factor) for code, label, factor in item["options"]}
        bad = [c for c in codes if c not in options]
        if bad:
            raise ValueError(f"{link_id}: {bad} not among {list(options)}")
        if len(codes) > 1 and not item["multiple"]:
            raise ValueError(f"{link_id} takes one answer, got {codes}")
        if not codes and not text:
            continue
        rows.append({"linkId": link_id, "codes": codes, "labels": [options[c][0] for c in codes],
                     "text": text, "riskFactor": any(options[c][1] for c in codes),
                     "risks": item["risks"], "basedOn": based_on})
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
