"""Anamnesis protocols: validated questionnaires and structured history, coded, prefilled from the data.

The data-driven anamnesis (anamnesis.py) asks what a finding in the values raises.
This module adds the other half, its own category in the graph: published
instruments that doctors and studies use, so an answer means the same here as in
a guideline, a trial or a Patient Summary.

Scores (validated, with published points and bands):
  Life's Essential 8 (AHA 2022)   heart health, eight metrics of 0 to 100
  FINDRISC (2003)                 10-year risk of type 2 diabetes
  AUDIT-C (1998)                  alcohol, the WHO AUDIT's three consumption items
  MEDAS-14 (PREDIMED, 2011)       closeness to a Mediterranean diet
  PHQ-2 (2003)                    two-item mood screen (tiredness is often low mood)
Structured history (coded as FHIR does, no score):
  Tobacco use                     as in the International Patient Summary (LOINC 72166-2)
  Family history of heart disease the ESC 2021 rule: premature means men before 55, women before 65
  Lipid-lowering medication       with dates, so values measured under it are read as treated
  Eating pattern and fasting      keto, low-carb, Mediterranean, plant-based, fasting

Every item carries its LOINC question code where one exists and every answer the
SNOMED CT concept it asserts (verified on tx.fhir.org and the CSIRO Ontoserver,
International Edition, Nov 2026). STOP-Bang is left out: University Health Network
licenses it and asks for permission even for clinical use.

Prefilled, personalised: `plan()` answers what the graph already holds (age, BMI,
waist, non-HDL cholesterol, HbA1c, blood pressure, Apple Watch exercise minutes and
sleep, earlier answers), says where each prefilled answer comes from, ranks the
protocols by the person's own findings and computes the score so far with the range
it can still reach. The person confirms or changes the prefilled answers.

In the graph:

  (:AnamnesisCategory)-[:HAS_PROTOCOL]->(:AnamnesisProtocol)-[:HAS_ITEM]->(:ProtocolItem)
  (:AnamnesisProtocol)-[:INFORMS]->(:HealthRisk)
  (:AnamnesisProtocol|ProtocolItem)-[:CODED_BY]->(:LoincCode | :SnomedCode)
  (:ProtocolItem)-[:ANSWER_CODE {option}]->(:SnomedCode)
  (:Patient)-[:HAS_RESPONSE]->(:QuestionnaireResponse {protocol, score, band})-[:RESPONDS_TO]->(:AnamnesisProtocol)
  (:QuestionnaireResponse)-[:HAS_ANSWER]->(:Answer)-[:ANSWERS]->(:ProtocolItem)
  (:Answer)-[:CODED_BY]->(:SnomedCode)            what the answer asserts
  (:Answer)-[:PREFILLED_FROM]->(:Observation)     the value it was read from, when prefilled
  (:QuestionnaireResponse)-[:RISK_FACTOR_FOR]->(:HealthRisk)   when the band is a risk

Answers use the Answer nodes of the data-driven anamnesis, so a shared question
(smoking, lipid-medication, family-lipids, family-cvd) answered here is not asked
there again, and SCORE2 takes smoking from it. The protocols are generic; answers
go only into the person's own store.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

CATEGORY = {"id": "anamnesis-protocols", "name": "Anamnesis protocols",
            "description": "Validated questionnaires and structured history, coded with LOINC and SNOMED CT, "
                           "prefilled from the person's own data."}

# Every SNOMED CT concept used, with its semantic tag (International Edition; all active, Nov 2026).
SNOMED = {
    # assessment scales and scores
    "443313003": ("Finnish diabetes risk score", "assessment scale"),
    "763117005": ("FINDRISC (Finnish Diabetes Risk Score) score", "observable entity"),
    "273265007": ("Alcohol use disorders identification test", "assessment scale"),
    "763256006": ("AUDIT-C (Alcohol Use Disorders Identification Test - Consumption) score", "observable entity"),
    "1359725005": ("Patient Health Questionnaire-2", "assessment scale"),
    "1359723003": ("PHQ-2 (Patient Health Questionnaire-2) score", "observable entity"),
    # observables (what an item asks)
    "60621009": ("Body mass index", "observable entity"),
    "276361009": ("Waist circumference", "observable entity"),
    "68130003": ("Physical activity", "observable entity"),
    "248263006": ("Duration of sleep", "observable entity"),
    "75367002": ("Blood pressure", "observable entity"),
    "230056004": ("Cigarette consumption", "observable entity"),
    "391129005": ("Fruit and vegetable intake", "observable entity"),
    # findings, situations, regimes (what an answer asserts)
    "35425004": ("Normal body mass index", "finding"),
    "238131007": ("Overweight", "finding"),
    "162864005": ("Body mass index 30+ - obesity", "finding"),
    "408512008": ("Body mass index 40+ - severely obese", "finding"),
    "228447005": ("Physically active", "finding"),
    "415510005": ("Sedentary lifestyle", "finding"),
    "308116003": ("Antihypertensive therapy", "procedure"),
    "80394007": ("Hyperglycemia", "disorder"),
    "714628002": ("Prediabetes", "disorder"),
    "160303001": ("Family history of diabetes mellitus", "situation"),
    "105542008": ("Current non-drinker of alcohol", "finding"),
    "219006": ("Current drinker of alcohol", "finding"),
    "160593006": ("Alcohol intake within recommended sensible limits", "finding"),
    "160592001": ("Alcohol intake above recommended sensible limits", "finding"),
    "266919005": ("Never smoked tobacco", "finding"),
    "8517006": ("Ex-smoker", "finding"),
    "735128000": ("Ex-smoker for less than 1 year", "finding"),
    "77176002": ("Smoker", "finding"),
    "230059006": ("Occasional cigarette smoker", "finding"),
    "160603005": ("Light cigarette smoker (1-9 cigs/day)", "finding"),
    "160604004": ("Moderate cigarette smoker (10-19 cigs/day)", "finding"),
    "160605003": ("Heavy cigarette smoker (20-39 cigs/day)", "finding"),
    "160606002": ("Very heavy cigarette smoker (40+ cigs/day)", "finding"),
    "722499006": ("Electronic cigarette user", "finding"),
    "43381005": ("Passive smoker", "finding"),
    "315213009": ("Not a passive smoker", "situation"),
    "266894000": ("Family history: Cardiovascular disease", "situation"),
    "439724007": ("Family history of cardiovascular disease in first degree male relative less than 55 years of age",
                  "situation"),
    "438825005": ("Family history of cardiovascular disease in first degree female relative less than 65 years of age",
                  "situation"),
    "160270001": ("No family history: Cardiovascular disease", "situation"),
    "443454007": ("Family history of familial hypercholesterolemia", "situation"),
    "134350008": ("Lipid-lowering therapy", "procedure"),
    "372912004": ("HMG-CoA reductase inhibitor", "substance"),
    "764637000": ("Lipid-lowering therapy stopped", "situation"),
    "1255163004": ("Mediterranean diet", "regime/therapy"),
    "66539004": ("Carbohydrate restricted diet", "finding"),
    "765060000": ("Ketogenic diet", "regime/therapy"),
    "765021002": ("Vegetarian diet", "regime/therapy"),
    "1255165006": ("Vegan diet", "regime/therapy"),
    "1362129009": ("Intermittent fasting", "finding"),
    "16985007": ("Fasting", "finding"),
}

# Sources quoted in the protocols' critical notes (PubMed, checked Nov 2026).
EVIDENCE = {
    "hackshaw-2018": {"citation": "Hackshaw et al., BMJ 2018;360:j5855", "pmid": "29367388",
                      "doi": "10.1136/bmj.j5855",
                      "finding": "One cigarette a day carries about half the excess risk of coronary heart disease "
                                 "and stroke of 20 a day (141 cohort studies)."},
    "zhao-2023": {"citation": "Zhao et al., JAMA Netw Open 2023;6:e236185", "pmid": "37000449",
                  "doi": "10.1001/jamanetworkopen.2023.6185",
                  "finding": "Occasional and low-volume drinkers did not live longer than lifetime non-drinkers "
                             "once the studies' biases were controlled (107 cohorts)."},
    "estruch-2018": {"citation": "Estruch et al., N Engl J Med 2018;378:e34 (PREDIMED, republished)",
                     "pmid": "29897866", "doi": "10.1056/NEJMoa1800389",
                     "finding": "A Mediterranean diet with extra olive oil or nuts lowered heart attacks, strokes and "
                                "cardiovascular deaths by about 30 % against a low-fat diet."},
    "esc-2021": {"citation": "Visseren et al., Eur Heart J 2021;42:3227 (ESC prevention guideline)",
                 "pmid": "34458905", "doi": "10.1093/eurheartj/ehab484",
                 "finding": "Family history counts as a risk modifier only when heart disease started early in a "
                            "first-degree relative: men before 55, women before 65."},
    "who-2020-activity": {"citation": "Bull et al., Br J Sports Med 2020;54:1451 (WHO guidelines)",
                          "pmid": "33239350", "doi": "10.1136/bjsports-2020-102955",
                          "finding": "Adults: 150 to 300 minutes of moderate or 75 to 150 of vigorous activity a week, "
                                     "and muscle strengthening on two or more days."},
}


def o(code: str, label: str, points: float | None = None, snomed: str | None = None, la: str | None = None,
      rf: bool = False) -> dict:
    """One answer option: its code, label, points, the SNOMED concept it asserts, its LOINC answer code."""
    return {"code": code, "label": label, "points": points, "snomed": snomed, "la": la, "riskFactor": rf}


YES_NO = lambda yes_points=1, no_points=0: [o("yes", "Yes", yes_points), o("no", "No", no_points)]

PROTOCOLS = [
    {"id": "le8", "name": "Life's Essential 8", "kind": "score", "year": 2022,
     "title": "American Heart Association: Life's Essential 8",
     "source": "Lloyd-Jones et al., Circulation 2022;146:e18", "pmid": "35766027",
     "doi": "10.1161/CIR.0000000000001078", "url": "https://doi.org/10.1161/CIR.0000000000001078",
     "licence": "Scoring published in an AHA presidential advisory; no licence needed to compute it.",
     "risks": ["cardiovascular", "diabetes", "fitness"], "method": "le8",
     "raisedBy": ["lipids", "glucose", "exercise_bp", "oxygen", "smoking_unknown"],
     "bands": [(0, "low", "low cardiovascular health"), (50, "moderate", "moderate cardiovascular health"),
               (80, "high", "high cardiovascular health")], "flagBelow": 50,
     "why": "The newest construct of heart health (2022), replacing Life's Simple 7: it adds sleep, uses non-HDL "
            "cholesterol and HbA1c, and scores each metric from 0 to 100, so a change shows before a disease does.",
     "critical": ["Diet is scored with the AHA's MEPA screener, which is not here; this score averages the seven "
                  "other metrics. MEDAS-14 below measures the Mediterranean pattern instead.",
                  "Apple Watch exercise minutes count brisk activity, not everyday walking, and LE8 counts vigorous "
                  "minutes twice: the watch tends to underestimate the activity score, not overestimate it."],
     "items": [
         {"linkId": "le8-activity", "metric": "activity", "snomed": "68130003", "prefill": "watch_minutes",
          "text": "Minutes per week of moderate or vigorous activity (vigorous minutes count twice)",
          "options": [o("150+", "150 or more", 100, "228447005"), o("120-149", "120 to 149", 90),
                      o("90-119", "90 to 119", 80), o("60-89", "60 to 89", 60), o("30-59", "30 to 59", 40),
                      o("1-29", "1 to 29", 20), o("0", "None", 0, "415510005")]},
         {"linkId": "le8-nicotine", "metric": "nicotine", "loinc": "72166-2", "prefill": "tobacco",
          "text": "Tobacco and nicotine",
          "options": [o("never", "Never smoked", 100, "266919005"), o("quit-5y", "Quit 5 or more years ago", 75, "8517006"),
                      o("quit-1y", "Quit 1 to 5 years ago", 50, "8517006"),
                      o("quit-recent", "Quit less than a year ago", 25, "735128000"),
                      o("vape", "E-cigarette or vape now, no cigarettes", 25, "722499006"),
                      o("current", "Smoke now, even occasionally", 0, "77176002", rf=True)]},
         {"linkId": "le8-home-smoke", "metric": "nicotine", "adjust": True, "prefill": "home_smoke",
          "text": "Does anyone smoke indoors where you live?",
          "options": [o("no", "No", 0, "315213009"), o("yes", "Yes", -20, "43381005")]},
         {"linkId": "le8-sleep", "metric": "sleep", "loinc": "93832-4", "snomed": "248263006", "prefill": "watch_sleep",
          "text": "Hours of sleep on an average night",
          "options": [o("7-9", "7 to under 9", 100), o("9-10", "9 to under 10", 90), o("6-7", "6 to under 7", 70),
                      o("5-6", "5 to under 6, or 10 or more", 40), o("4-5", "4 to under 5", 20), o("<4", "Under 4", 0)]},
         {"linkId": "le8-bmi", "metric": "bmi", "loinc": "39156-5", "snomed": "60621009", "prefill": "bmi",
          "text": "Body mass index (kg/m²)",
          "options": [o("<25", "Under 25", 100, "35425004"), o("25-30", "25 to 29.9", 70, "238131007"),
                      o("30-35", "30 to 34.9", 30, "162864005"), o("35-40", "35 to 39.9", 15, "162864005"),
                      o("40+", "40 or more", 0, "408512008")]},
         {"linkId": "le8-lipids", "metric": "lipids", "loinc": "43396-1", "prefill": "nonhdl",
          "text": "Non-HDL cholesterol",
          "options": [o("<130", "Under 130 mg/dL (3.4 mmol/L)", 100), o("130-159", "130 to 159 mg/dL", 60),
                      o("160-189", "160 to 189 mg/dL", 40), o("190-219", "190 to 219 mg/dL", 20),
                      o("220+", "220 mg/dL (5.7 mmol/L) or more", 0)]},
         {"linkId": "le8-lipid-drug", "metric": "lipids", "adjust": True, "prefill": "lipid_drug",
          "text": "Do you take cholesterol-lowering medicine now?",
          "options": [o("no", "No", 0), o("yes", "Yes", -20, "134350008")]},
         {"linkId": "le8-glucose", "metric": "glucose", "loinc": "4548-4", "prefill": "glucose",
          "text": "Blood sugar: HbA1c (or fasting glucose)",
          "options": [o("normal", "No diabetes, HbA1c under 5.7 % (glucose under 100 mg/dL)", 100),
                      o("prediabetes", "No diabetes, HbA1c 5.7 to 6.4 % (glucose 100 to 125)", 60, "714628002", rf=True),
                      o("dm<7", "Diabetes, HbA1c under 7.0 %", 40, rf=True), o("dm7", "Diabetes, HbA1c 7.0 to 7.9 %", 30, rf=True),
                      o("dm8", "Diabetes, HbA1c 8.0 to 8.9 %", 20, rf=True), o("dm9", "Diabetes, HbA1c 9.0 to 9.9 %", 10, rf=True),
                      o("dm10", "Diabetes, HbA1c 10 % or more", 0, rf=True)]},
         {"linkId": "le8-bp", "metric": "bp", "loinc": "85354-9", "snomed": "75367002", "prefill": "bp",
          "text": "Blood pressure",
          "options": [o("<120", "Under 120/80", 100), o("120-129", "120 to 129 and under 80", 75),
                      o("130-139", "130 to 139 or 80 to 89", 50), o("140-159", "140 to 159 or 90 to 99", 25, rf=True),
                      o("160+", "160 or 100 or higher", 0, rf=True)]},
         {"linkId": "le8-bp-drug", "metric": "bp", "adjust": True, "prefill": "bp_drug",
          "text": "Do you take blood pressure medicine?",
          "options": [o("no", "No", 0), o("yes", "Yes", -20, "308116003")]},
     ]},

    {"id": "findrisc", "name": "FINDRISC", "kind": "score", "year": 2003,
     "title": "Finnish Diabetes Risk Score", "source": "Lindström & Tuomilehto, Diabetes Care 2003;26:725",
     "pmid": "12610029", "doi": "10.2337/diacare.26.3.725", "url": "https://doi.org/10.2337/diacare.26.3.725",
     "licence": "Free to use; the German Diabetes Foundation's FINDRISK test is its translation.",
     "loinc": "97055-8", "scoreLoinc": "97064-0", "snomed": "443313003", "scoreSnomed": "763117005",
     "risks": ["diabetes"], "method": "sum", "raisedBy": ["glucose", "triglycerides", "liver_enzymes", "fib4"],
     "bands": [(0, "low", "about 1 in 100 develop type 2 diabetes within 10 years"),
               (7, "slightly elevated", "about 1 in 25 within 10 years"),
               (12, "moderate", "about 1 in 6 within 10 years"), (15, "high", "about 1 in 3 within 10 years"),
               (21, "very high", "about 1 in 2 within 10 years")], "flagFrom": 12,
     "why": "Europe's most used diabetes risk questionnaire (eight questions, no blood test); the German Diabetes "
            "Foundation uses it as FINDRISK.",
     "critical": ["'High blood glucose' here means HbA1c from 5.7 % or fasting glucose from 100 mg/dL (ADA 2025); "
                  "the WHO sets impaired fasting glucose from 110 mg/dL, so the same value can count in one and not "
                  "the other."],
     "items": [
         {"linkId": "findrisc-age", "prefill": "age", "text": "Age",
          "options": [o("<45", "Under 45", 0), o("45-54", "45 to 54", 2), o("55-64", "55 to 64", 3),
                      o("65+", "65 or older", 4)]},
         {"linkId": "findrisc-bmi", "loinc": "97057-4", "snomed": "60621009", "prefill": "bmi",
          "text": "Body mass index (kg/m²)",
          "options": [o("<25", "Under 25", 0, "35425004"), o("25-30", "25 to 30", 1, "238131007"),
                      o(">30", "Over 30", 3, "162864005", rf=True)]},
         {"linkId": "findrisc-waist", "loinc": "97058-2", "snomed": "276361009", "prefill": "waist",
          "text": "Waist circumference, measured below the ribs (usually at the navel)",
          "options": [o("small", "Men under 94 cm, women under 80 cm", 0),
                      o("medium", "Men 94 to 102 cm, women 80 to 88 cm", 3),
                      o("large", "Men over 102 cm, women over 88 cm", 4, rf=True)]},
         {"linkId": "findrisc-activity", "loinc": "97059-0", "prefill": "watch_daily30",
          "text": "Do you usually have at least 30 minutes of physical activity every day, at work or in your "
                  "free time (everyday activity counts)?",
          "options": [o("yes", "Yes", 0, "228447005"), o("no", "No", 2)]},
         {"linkId": "findrisc-vegetables", "loinc": "97060-8", "snomed": "391129005",
          "text": "How often do you eat vegetables, fruit or berries?",
          "options": [o("daily", "Every day", 0), o("not-daily", "Not every day", 1)]},
         {"linkId": "findrisc-bp-drugs", "prefill": "bp_drug",
          "text": "Have you ever taken blood pressure medicine regularly?",
          "options": [o("no", "No", 0), o("yes", "Yes", 2, "308116003")]},
         {"linkId": "findrisc-glucose", "loinc": "97062-4", "prefill": "glucose_ever_high",
          "text": "Have you ever been found to have high blood glucose (in a check-up, during an illness, in "
                  "pregnancy)?",
          "options": [o("no", "No", 0), o("yes", "Yes", 5, "80394007", rf=True)]},
         {"linkId": "findrisc-family", "loinc": "97063-2", "prefill": "family_diabetes",
          "text": "Has anyone in your family been diagnosed with diabetes (type 1 or type 2)?",
          "options": [o("no", "No", 0),
                      o("distant", "Yes: grandparent, aunt, uncle or first cousin", 3, "160303001"),
                      o("close", "Yes: parent, brother, sister or my own child", 5, "160303001", rf=True)]},
     ]},

    {"id": "audit-c", "name": "AUDIT-C", "kind": "score", "year": 1998,
     "title": "Alcohol Use Disorders Identification Test, consumption questions",
     "source": "Bush et al., Arch Intern Med 1998;158:1789 (from the WHO AUDIT)", "pmid": "9738608",
     "doi": "10.1001/archinte.158.16.1789", "url": "https://doi.org/10.1001/archinte.158.16.1789",
     "licence": "The WHO AUDIT is free to use.",
     "loinc": "72109-2", "scoreLoinc": "75626-2", "snomed": "273265007", "scoreSnomed": "763256006",
     "risks": ["liver", "cardiovascular"], "method": "sum", "raisedBy": ["liver_enzymes", "fib4", "triglycerides"],
     "cutOff": {"male": 4, "female": 3, "any": 4},
     "bands": [(0, "below the cut-off", "no sign of hazardous drinking"),
               (3, "at or above the cut-off", "hazardous drinking is likely: talk about it with your doctor")],
     "bandSnomed": ["160593006", "160592001"],
     "why": "The three consumption questions of the WHO's AUDIT: the screen most primary care and EU guidance use.",
     "critical": ["No safe minimum is proven: occasional and low-volume drinkers did not live longer than lifetime "
                  "non-drinkers once the studies' biases were controlled (Zhao 2023). The ESC 2021 prevention "
                  "guideline advises at most 100 g of alcohol a week."],
     "evidence": ["zhao-2023"],
     "items": [
         {"linkId": "audit-c-1", "loinc": "68518-0", "prefill": "alcohol_none",
          "text": "How often do you have a drink containing alcohol?",
          "options": [o("never", "Never", 0, "105542008", "LA6270-8"),
                      o("monthly", "Monthly or less", 1, "219006", "LA18926-8"),
                      o("2-4-month", "2 to 4 times a month", 2, "219006", "LA18927-6"),
                      o("2-3-week", "2 to 3 times a week", 3, "219006", "LA18928-4"),
                      o("4-week", "4 or more times a week", 4, "219006", "LA18929-2")]},
         {"linkId": "audit-c-2", "loinc": "68519-8", "skipIf": {"audit-c-1": "never"},
          "text": "How many standard drinks do you have on a typical day when you drink (one = a small beer or "
                  "a small glass of wine)?",
          "options": [o("1-2", "1 or 2", 0, None, "LA15694-5"), o("3-4", "3 or 4", 1, None, "LA15695-2"),
                      o("5-6", "5 or 6", 2, None, "LA18930-0"), o("7-9", "7 to 9", 3, None, "LA18931-8"),
                      o("10+", "10 or more", 4, None, "LA18932-6")]},
         {"linkId": "audit-c-3", "loinc": "68520-6", "skipIf": {"audit-c-1": "never"},
          "text": "How often do you have 6 or more drinks on one occasion?",
          "options": [o("never", "Never", 0, None, "LA6270-8"), o("less-monthly", "Less than monthly", 1, None, "LA18933-4"),
                      o("monthly", "Monthly", 2, None, "LA18876-5"), o("weekly", "Weekly", 3, None, "LA18891-4"),
                      o("daily", "Daily or almost daily", 4, None, "LA18934-2")]},
     ]},

    {"id": "tobacco", "name": "Tobacco use", "kind": "history", "year": 2024,
     "title": "Tobacco use, as the International Patient Summary records it",
     "source": "HL7 FHIR International Patient Summary, social history (the EHDS Patient Summary follows it)",
     "url": "https://hl7.org/fhir/uv/ips/", "licence": "Codes: LOINC and SNOMED CT (affiliate licence).",
     "loinc": "72166-2", "risks": ["cardiovascular", "kidney", "bone", "diabetes"],
     "raisedBy": ["smoking_unknown", "lipids", "lpa"],
     "why": "Smoking status is the one SCORE2 input the graph cannot know; coded as the Patient Summary does, it "
            "travels with the person's record across Europe.",
     "critical": ["SCORE2 knows only smoker or not, and counts any current smoking. One cigarette a day already "
                  "carries about half the heart and stroke risk of 20 a day (Hackshaw 2018); there is no study "
                  "showing a safe lower amount."],
     "evidence": ["hackshaw-2018"],
     "items": [
         {"linkId": "smoking", "loinc": "72166-2", "prefill": "answer:smoking", "text": "Do you smoke, or did you?",
          "options": [o("never", "Never", None, "266919005"), o("former", "Former smoker", None, "8517006"),
                      o("current", "Current smoker, even occasionally", None, "77176002", rf=True)]},
         {"linkId": "tobacco-amount", "snomed": "230056004", "enableWhen": {"smoking": "current"},
          "text": "How much do you smoke?",
          "options": [o("occasional", "Less than one cigarette a day", None, "230059006", rf=True),
                      o("1-9", "1 to 9 a day", None, "160603005", rf=True),
                      o("10-19", "10 to 19 a day", None, "160604004", rf=True),
                      o("20-39", "20 to 39 a day", None, "160605003", rf=True),
                      o("40+", "40 or more a day", None, "160606002", rf=True)]},
         {"linkId": "tobacco-quit", "enableWhen": {"smoking": "former"}, "text": "When did you stop?",
          "options": [o("<1y", "Less than a year ago", None, "735128000"), o("1-5y", "1 to 5 years ago", None, "8517006"),
                      o("5y+", "5 or more years ago", None, "8517006")]},
         {"linkId": "tobacco-vape", "text": "Do you use e-cigarettes or vapes?",
          "options": [o("no", "No"), o("yes", "Yes", None, "722499006")]},
         {"linkId": "tobacco-home", "text": "Does anyone smoke indoors where you live?",
          "options": [o("no", "No", None, "315213009"), o("yes", "Yes", None, "43381005", rf=True)]},
     ]},

    {"id": "medas", "name": "MEDAS-14", "kind": "score", "year": 2011,
     "title": "Mediterranean Diet Adherence Screener (PREDIMED)",
     "source": "Schröder et al., J Nutr 2011;141:1140", "pmid": "21508208", "doi": "10.3945/jn.110.135566",
     "url": "https://doi.org/10.3945/jn.110.135566", "licence": "Published screener; questions here are paraphrased.",
     "snomed": "1255163004", "risks": ["cardiovascular", "diabetes"], "method": "sum",
     "raisedBy": ["lipids", "triglycerides", "glucose", "liver_enzymes"],
     "bands": [(0, "low adherence", "far from the Mediterranean pattern"),
               (6, "moderate adherence", "partly Mediterranean"),
               (10, "high adherence", "close to the pattern tested in PREDIMED")], "flagBelow": 6,
     "why": "The 14 questions of PREDIMED, the trial in which a Mediterranean diet lowered heart attacks and strokes "
            "(Estruch 2018); quick, and validated against a full food questionnaire.",
     "critical": ["One point is for 7 or more glasses of wine a week. That was the 2011 view; newer evidence finds no "
                  "benefit from drinking (Zhao 2023). The score is kept as published, but do not start drinking for it.",
                  "The score measures resemblance to the Mediterranean pattern. A ketogenic or low-carb diet scores low "
                  "on fruit and legumes whatever its other effects."],
     "evidence": ["estruch-2018", "zhao-2023"],
     "items": [
         {"linkId": "medas-1", "text": "Is olive oil your main cooking fat?", "options": YES_NO()},
         {"linkId": "medas-2", "text": "Do you use 4 or more tablespoons of olive oil a day (cooking, salads, eating out)?",
          "options": YES_NO()},
         {"linkId": "medas-3", "text": "Do you eat 2 or more servings of vegetables a day (at least one raw or as salad)?",
          "options": YES_NO()},
         {"linkId": "medas-4", "text": "Do you eat 3 or more pieces of fruit a day?", "options": YES_NO()},
         {"linkId": "medas-5", "text": "Do you eat less than one serving of red meat, burgers or sausage a day?",
          "options": YES_NO()},
         {"linkId": "medas-6", "text": "Do you have less than one serving of butter, margarine or cream a day?",
          "options": YES_NO()},
         {"linkId": "medas-7", "text": "Do you drink less than one sweet or fizzy drink a day?", "options": YES_NO()},
         {"linkId": "medas-8", "text": "Do you drink 7 or more glasses of wine a week? (see the note: no reason to start)",
          "prefill": "wine_week", "options": YES_NO()},
         {"linkId": "medas-9", "text": "Do you eat 3 or more servings of legumes (lentils, beans, chickpeas) a week?",
          "options": YES_NO()},
         {"linkId": "medas-10", "text": "Do you eat 3 or more servings of fish or seafood a week?", "options": YES_NO()},
         {"linkId": "medas-11", "text": "Do you eat shop-bought sweets or pastries less than 3 times a week?",
          "options": YES_NO()},
         {"linkId": "medas-12", "text": "Do you eat 3 or more servings of nuts a week?", "options": YES_NO()},
         {"linkId": "medas-13", "text": "Do you prefer chicken, turkey or rabbit to beef, pork, burgers or sausage?",
          "options": YES_NO()},
         {"linkId": "medas-14", "text": "Do you have dishes with a tomato, onion or garlic sauce simmered in olive oil "
                                        "2 or more times a week?", "options": YES_NO()},
     ]},

    {"id": "family-cvd", "name": "Family history of heart disease", "kind": "history", "year": 2021,
     "title": "Family history (FHIR FamilyMemberHistory), read by the ESC 2021 rule",
     "source": "Visseren et al., Eur Heart J 2021;42:3227 (ESC prevention guideline)", "pmid": "34458905",
     "doi": "10.1093/eurheartj/ehab484", "url": "https://doi.org/10.1093/eurheartj/ehab484",
     "licence": "Codes: SNOMED CT (affiliate licence).", "loinc": "10157-6", "risks": ["cardiovascular"],
     "raisedBy": ["lipids", "lpa"],
     "method": "family",
     "why": "Which relative and at what age decides whether a family history counts: ESC 2021 uses it as a risk "
            "modifier only when heart disease began early.",
     "critical": ["Heart disease that starts at 70 or later is common and does not count as a family history in "
                  "ESC 2021. Families share habits as well as genes: parents who smoked, did not exercise or ate "
                  "badly pass on less risk than the same disease at 50 would."],
     "evidence": ["esc-2021"],
     "items": [
         {"linkId": "family-cvd-who", "multiple": True,
          "text": "Who had a heart attack, a stroke, a bypass or a stent?",
          "options": [o("none", "Nobody", None, "160270001"), o("father", "Father"), o("mother", "Mother"),
                      o("brother", "A brother"), o("sister", "A sister"), o("unknown", "Not sure")]},
         {"linkId": "family-cvd-father-age", "enableWhen": {"family-cvd-who": "father"},
          "text": "How old was your father the first time?",
          "options": [o("<55", "Under 55", None, "439724007", rf=True), o("55-64", "55 to 64", None, "266894000"),
                      o("65+", "65 or older", None, "266894000"), o("unknown", "Not sure")]},
         {"linkId": "family-cvd-mother-age", "enableWhen": {"family-cvd-who": "mother"},
          "text": "How old was your mother the first time?",
          "options": [o("<65", "Under 65", None, "438825005", rf=True), o("65+", "65 or older", None, "266894000"),
                      o("unknown", "Not sure")]},
         {"linkId": "family-cvd-sibling-age", "enableWhen": {"family-cvd-who": ["brother", "sister"]},
          "text": "Was it early: a brother before 55 or a sister before 65?",
          "options": [o("yes", "Yes", None, None, rf=True), o("no", "No", None, "266894000"), o("unknown", "Not sure")]},
         {"linkId": "family-lipids", "prefill": "answer:family-lipids",
          "text": "Is familial hypercholesterolaemia, very high cholesterol or high Lp(a) known in your family?",
          "options": [o("yes", "Yes", None, "443454007", rf=True), o("no", "No"), o("unknown", "Not sure")]},
     ]},

    {"id": "lipid-therapy", "name": "Lipid-lowering medication", "kind": "history", "year": 2025,
     "title": "Cholesterol-lowering medicine and when (FHIR MedicationStatement)",
     "source": "ESC/EAS 2025 focused update on dyslipidaemias", "url": "https://doi.org/10.1093/eurheartj/ehaf190",
     "licence": "Codes: SNOMED CT (affiliate licence).", "snomed": "134350008", "risks": ["cardiovascular"],
     "raisedBy": ["lipids"],
     "why": "Lipid values measured under a statin show the medicine, not the person: with the dates, the graph can "
            "tell treated values from untreated ones.",
     "critical": ["A statin lowers LDL cholesterol by 30 to 50 % within weeks. The lowest value in a series is "
                  "often the treated one; the untreated level is what the risk scores assume unless told otherwise."],
     "items": [
         {"linkId": "lipid-medication", "prefill": "answer:lipid-medication",
          "text": "Do you take, or did you take, medication to lower cholesterol?",
          "options": [o("none", "Never"), o("statin", "A statin", None, "372912004"),
                      o("combination", "Statin plus ezetimibe or another drug", None, "134350008"),
                      o("stopped", "I took one and stopped", None, "764637000")]},
         {"linkId": "lipid-from", "type": "month", "enableWhen": {"lipid-medication": ["statin", "combination", "stopped"]},
          "text": "Since when (year and month)?", "options": []},
         {"linkId": "lipid-until", "type": "month", "enableWhen": {"lipid-medication": "stopped"},
          "text": "Until when (year and month)?", "options": []},
     ]},

    {"id": "diet-pattern", "name": "Eating pattern and fasting", "kind": "history", "year": 2025,
     "title": "Eating pattern and fasting, coded with SNOMED CT",
     "source": "SNOMED CT International Edition", "licence": "Codes: SNOMED CT (affiliate licence).",
     "risks": ["cardiovascular", "diabetes", "liver"], "raisedBy": ["lipids", "triglycerides", "glucose", "liver_enzymes"],
     "why": "The diet changes how lipid, glucose and liver values read: a ketogenic diet lowers triglycerides and "
            "raises HDL, and in some people raises LDL cholesterol and ApoB a lot.",
     "critical": ["Under a low-carb or ketogenic diet, read LDL and ApoB with the diet in mind; triglycerides and the "
                  "TG/HDL ratio then look better than they would on a mixed diet."],
     "items": [
         {"linkId": "diet-pattern", "text": "How do you eat, mostly?",
          "options": [o("mixed", "Mixed"), o("mediterranean", "Mediterranean", None, "1255163004"),
                      o("low-carb", "Low-carb", None, "66539004"), o("keto", "Ketogenic", None, "765060000"),
                      o("vegetarian", "Vegetarian", None, "765021002"), o("vegan", "Vegan", None, "1255165006")]},
         {"linkId": "fasting-habit", "text": "Do you fast regularly?",
          "options": [o("no", "No"), o("time-restricted", "Time-restricted eating (e.g. 16:8)", None, "1362129009"),
                      o("long", "Fasts of a day or more", None, "16985007")]},
     ]},

    {"id": "phq-2", "name": "PHQ-2", "kind": "score", "year": 2003,
     "title": "Patient Health Questionnaire, two questions", "source": "Kroenke et al., Med Care 2003;41:1284",
     "pmid": "14583691", "url": "https://pubmed.ncbi.nlm.nih.gov/14583691/",
     "licence": "Free to use (PHQ screeners: no permission required).",
     "loinc": "55757-9", "scoreLoinc": "55758-7", "snomed": "1359725005", "scoreSnomed": "1359723003",
     "risks": ["cardiovascular", "fitness"], "method": "sum", "raisedBy": [],
     "bands": [(0, "below the cut-off", "no sign of low mood"),
               (3, "at or above the cut-off", "low mood is possible: the full PHQ-9 or a doctor can tell")],
     "flagFrom": 3,
     "why": "Feeling tired all the time is often low mood, not a missing lab value; two questions screen for it "
            "before more tests are ordered.",
     "critical": ["A screen, not a diagnosis. ESC 2021 counts depression among the factors that raise heart risk."],
     "items": [
         {"linkId": "phq2-1", "loinc": "44250-9", "text": "Over the last two weeks: little interest or pleasure in "
                                                         "doing things?",
          "options": [o("0", "Not at all", 0, None, "LA6568-5"), o("1", "Several days", 1, None, "LA6569-3"),
                      o("2", "More than half the days", 2, None, "LA6570-1"),
                      o("3", "Nearly every day", 3, None, "LA6571-9")]},
         {"linkId": "phq2-2", "loinc": "44255-8", "text": "Over the last two weeks: feeling down, depressed or hopeless?",
          "options": [o("0", "Not at all", 0, None, "LA6568-5"), o("1", "Several days", 1, None, "LA6569-3"),
                      o("2", "More than half the days", 2, None, "LA6570-1"),
                      o("3", "Nearly every day", 3, None, "LA6571-9")]},
     ]},
]
PROTOCOL = {p["id"]: p for p in PROTOCOLS}
ITEM = {(p["id"], i["linkId"]): i for p in PROTOCOLS for i in p["items"]}

# What each prefill reads, said once (shown in the graph and to Claude).
PREFILL = {
    "age": "your age, from the year of birth you shared",
    "bmi": "your newest body mass index, else your newest weight and height",
    "waist": "your newest waist circumference",
    "watch_minutes": "Apple Watch exercise minutes, the mean of the last 12 weeks",
    "watch_daily30": "Apple Watch exercise minutes: yes when the 12-week mean is 30 minutes a day or more",
    "watch_sleep": "Apple Watch sleep, the mean of the last 12 weeks",
    "nonhdl": "your newest non-HDL cholesterol, else total minus HDL cholesterol of one day",
    "glucose": "your newest HbA1c, else fasting glucose",
    "glucose_ever_high": "every HbA1c and glucose value: yes when one reached 5.7 % or 100 mg/dL",
    "bp": "your newest blood pressure reading",
    "bp_drug": "your anamnesis answer about blood pressure treatment",
    "lipid_drug": "your answer about cholesterol-lowering medicine",
    "tobacco": "your smoking answers",
    "home_smoke": "your answer about smoking at home",
    "family_diabetes": "your anamnesis answer about diabetes in parents and siblings",
    "alcohol_none": "your anamnesis answer about alcohol",
    "wine_week": "your anamnesis answer about alcohol",
}

# ── reading the person's data ────────────────────────────────────────────────

NEWEST = """
MATCH (p:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(c:LoincCode)
WHERE c.code IN $codes AND o.duplicateOf IS NULL AND o.valueQuantity IS NOT NULL
  AND coalesce(o.sourceKind, '') <> 'device-weekly-mean'
RETURN o.resourceId AS id, c.code AS code, o.valueQuantity AS value, o.unit AS unit, o.effectiveDate AS date
ORDER BY o.effectiveDate DESC
"""

DEVICE_MEAN = """
MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(:LoincCode {code: $code})
WHERE o.sourceKind = 'device-weekly-mean' AND o.effectiveDate >= $since AND o.valueQuantity IS NOT NULL
RETURN count(o) AS weeks, avg(o.valueQuantity) AS mean, min(o.effectiveDate) AS first, max(o.effectiveDate) AS last
"""

PERSON = "MATCH (p:Patient) RETURN p.id AS id, p.birthYear AS birthYear, p.gender AS sex"

LATEST_ANSWERS = """
MATCH (:Patient)-[:HAS_RESPONSE]->(:QuestionnaireResponse)-[:HAS_ANSWER]->(a:Answer)
WITH a.linkId AS linkId, a ORDER BY a.authored DESC
WITH linkId, collect(a)[0] AS a
RETURN linkId, a.codes AS codes, a.labels AS labels, a.text AS text, a.authored AS authored
"""

RESPONSES = """
MATCH (:Patient)-[:HAS_RESPONSE]->(r:QuestionnaireResponse)
WHERE r.protocol IS NOT NULL
WITH r.protocol AS protocol, r ORDER BY r.authored DESC
WITH protocol, collect(r)[0] AS r
RETURN protocol, r.authored AS authored, r.score AS score, r.band AS band
"""

MG_PER_MMOL = {"chol": 38.67, "glucose": 18.016}


def _rows(conn, cypher: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in conn.execute(cypher, params or {})]


def _unit(u: str | None) -> str:
    return (u or "").lower().replace(" ", "").replace("µ", "u")


def _mg(value: float, unit: str | None, kind: str) -> float | None:
    """mg/dL from mg/dL or mmol/L; None for a unit we do not know."""
    u = _unit(unit)
    if u in ("mg/dl",):
        return value
    if u in ("mmol/l",):
        return value * MG_PER_MMOL[kind]
    return None


def _hba1c_percent(value: float, unit: str | None) -> float | None:
    u = _unit(unit)
    if u in ("%", "%hb", "%{hb}"):
        return value
    if u in ("mmol/mol",):
        return round(0.09148 * value + 2.152, 1)  # IFCC to NGSP (DCCT) master equation
    return None


def _source(row: dict, text: str) -> dict:
    return {"observation": row.get("id"), "date": row.get("date"), "text": text}


def facts(conn, today: str) -> dict:
    """What the graph holds that the protocols can use, each with where it came from."""
    t = dt.date.fromisoformat(today)
    since = (t - dt.timedelta(days=84)).isoformat()
    person = (_rows(conn, PERSON) or [{}])[0]
    f: dict = {"person": person}
    if person.get("birthYear"):
        f["age"] = {"value": t.year - person["birthYear"], "text": f"year of birth {person['birthYear']}"}

    def newest(codes):
        rows = _rows(conn, NEWEST, {"codes": codes})
        return rows[0] if rows else None

    if r := newest(["39156-5"]):
        f["bmi"] = {"value": round(r["value"], 1), **_source(r, f"BMI {r['value']:g} on {r['date']}")}
    else:
        w, h = newest(["29463-7"]), newest(["8302-2"])
        if w and h and _unit(w["unit"]) == "kg" and _unit(h["unit"]) in ("cm", "m"):
            metres = h["value"] / 100 if _unit(h["unit"]) == "cm" else h["value"]
            bmi = round(w["value"] / metres ** 2, 1)
            f["bmi"] = {"value": bmi, **_source(w, f"BMI {bmi:g} from {w['value']:g} kg on {w['date']} and "
                                                  f"{h['value']:g} {h['unit']}")}
    if r := newest(["8280-0", "56086-2"]):
        if _unit(r["unit"]) == "cm":
            f["waist"] = {"value": r["value"], **_source(r, f"waist {r['value']:g} cm on {r['date']}")}
    # Non-HDL: measured, else total minus HDL of the same day.
    if r := newest(["43396-1", "70204-3"]):
        mg = _mg(r["value"], r["unit"], "chol")
        if mg is not None:
            f["nonhdl"] = {"value": round(mg), **_source(r, f"non-HDL cholesterol {r['value']:g} {r['unit']} on {r['date']}")}
    if "nonhdl" not in f:
        tcs, hdls = _rows(conn, NEWEST, {"codes": ["2093-3", "14647-2"]}), _rows(conn, NEWEST, {"codes": ["2085-9", "14646-4"]})
        for tc in tcs:
            hdl = next((h for h in hdls if h["date"] == tc["date"]), None)
            if hdl:
                a, b = _mg(tc["value"], tc["unit"], "chol"), _mg(hdl["value"], hdl["unit"], "chol")
                if a is not None and b is not None:
                    f["nonhdl"] = {"value": round(a - b), **_source(
                        tc, f"total {tc['value']:g} minus HDL {hdl['value']:g} {tc['unit']} on {tc['date']}")}
                    break
    # Glucose: newest HbA1c, else fasting glucose; and whether any value was ever high.
    a1c = [dict(r, pct=_hba1c_percent(r["value"], r["unit"])) for r in _rows(conn, NEWEST, {"codes": ["4548-4", "17856-6"]})]
    a1c = [r for r in a1c if r["pct"] is not None]
    glu = [dict(r, mg=_mg(r["value"], r["unit"], "glucose")) for r in _rows(conn, NEWEST, {"codes": ["1558-6", "2345-7"]})]
    glu = [r for r in glu if r["mg"] is not None]
    if a1c:
        r = a1c[0]
        f["glucose"] = {"hba1c": r["pct"], **_source(r, f"HbA1c {r['value']:g} {r['unit']} on {r['date']}")}
    elif glu:
        r = glu[0]
        f["glucose"] = {"mg": round(r["mg"]), **_source(r, f"glucose {r['value']:g} {r['unit']} on {r['date']}")}
    high = [r for r in a1c if r["pct"] >= 5.7] + [r for r in glu if r["mg"] >= 100]
    if high:
        r = max(high, key=lambda x: x["date"])
        f["glucose_ever_high"] = {"value": True, **_source(
            r, f"{'HbA1c' if 'pct' in r else 'glucose'} {r['value']:g} {r['unit']} on {r['date']}")}
    elif a1c or glu:
        n = len(a1c) + len(glu)
        f["glucose_ever_high"] = {"value": False, **_source((a1c + glu)[0], f"all {n} HbA1c and glucose values below "
                                                                          "5.7 % and 100 mg/dL")}
    sys_rows, dia_rows = _rows(conn, NEWEST, {"codes": ["8480-6"]}), _rows(conn, NEWEST, {"codes": ["8462-4"]})
    for s in sys_rows:
        d = next((x for x in dia_rows if x["date"] == s["date"]), None)
        if d:
            f["bp"] = {"sys": s["value"], "dia": d["value"], **_source(s, f"{s['value']:g}/{d['value']:g} mmHg on {s['date']}")}
            break
    for key, code, unit in (("watch_minutes", "55411-3", "min/d"), ("watch_sleep", "93832-4", "h/d")):
        r = (_rows(conn, DEVICE_MEAN, {"code": code, "since": since}) or [{}])[0]
        if (r.get("weeks") or 0) >= 4 and r.get("mean") is not None:
            f[key] = {"value": round(r["mean"], 1), "weeks": r["weeks"], "observation": None, "date": r["last"],
                      "text": f"Apple Watch, mean {r['mean']:.1f} {unit} over {r['weeks']} weeks to {r['last']}"}
    f["answers"] = {r["linkId"]: r for r in _rows(conn, LATEST_ANSWERS)}
    return f


def _band(value: float, cuts: list[tuple[float, str]]) -> str:
    """The option code of the first cut the value is below; the last code otherwise."""
    for limit, code in cuts:
        if value < limit:
            return code
    return cuts[-1][1]


def _answer(f: dict, link_id: str) -> list[str]:
    a = f["answers"].get(link_id)
    return list(a["codes"] or []) if a else []


def prefill_value(name: str, protocol: dict, item: dict, f: dict) -> dict | None:
    """{"code", "text", "observation", "date"} for one item, or None when the graph does not know."""
    def out(code, src):
        return {"code": code, "text": src.get("text"), "observation": src.get("observation"), "date": src.get("date")}

    if name == "age" and "age" in f:
        return out(_band(f["age"]["value"], [(45, "<45"), (55, "45-54"), (65, "55-64"), (999, "65+")]), f["age"])
    if name == "bmi" and "bmi" in f:
        v = f["bmi"]["value"]
        cuts = ([(25, "<25"), (30, "25-30"), (35, "30-35"), (40, "35-40"), (999, "40+")] if protocol["id"] == "le8"
                else [(25, "<25"), (30.0001, "25-30"), (999, ">30")])
        return out(_band(v, cuts), f["bmi"])
    if name == "waist" and "waist" in f:
        female = (f["person"].get("sex") or "").lower() == "female"
        lo, hi = (80, 88) if female else (94, 102)
        v = f["waist"]["value"]
        return out("small" if v < lo else "medium" if v <= hi else "large", f["waist"])
    if name == "watch_minutes" and "watch_minutes" in f:
        week = f["watch_minutes"]["value"] * 7
        return out(_band(week, [(1, "0"), (30, "1-29"), (60, "30-59"), (90, "60-89"), (120, "90-119"),
                                (150, "120-149"), (1e9, "150+")]), f["watch_minutes"])
    if name == "watch_daily30" and "watch_minutes" in f and f["watch_minutes"]["value"] >= 30:
        return out("yes", f["watch_minutes"])  # below 30 the watch may miss everyday activity: ask
    if name == "watch_sleep" and "watch_sleep" in f:
        h = f["watch_sleep"]["value"]
        code = "5-6" if h >= 10 else _band(h, [(4, "<4"), (5, "4-5"), (6, "5-6"), (7, "6-7"), (9, "7-9"), (10, "9-10")])
        return out(code, f["watch_sleep"])
    if name == "nonhdl" and "nonhdl" in f:
        return out(_band(f["nonhdl"]["value"], [(130, "<130"), (160, "130-159"), (190, "160-189"), (220, "190-219"),
                                                (1e9, "220+")]), f["nonhdl"])
    if name == "glucose" and "glucose" in f:
        g = f["glucose"]
        if "hba1c" in g:
            if g["hba1c"] >= 6.5:
                return None  # diabetes range: whether it is diagnosed diabetes is the person's to say
            return out("normal" if g["hba1c"] < 5.7 else "prediabetes", g)
        if g["mg"] >= 126:
            return None
        return out("normal" if g["mg"] < 100 else "prediabetes", g)
    if name == "glucose_ever_high" and "glucose_ever_high" in f:
        return out("yes" if f["glucose_ever_high"]["value"] else "no", f["glucose_ever_high"])
    if name == "bp" and "bp" in f:
        s, d = f["bp"]["sys"], f["bp"]["dia"]
        code = ("160+" if s >= 160 or d >= 100 else "140-159" if s >= 140 or d >= 90 else
                "130-139" if s >= 130 or d >= 80 else "120-129" if s >= 120 else "<120")
        return out(code, f["bp"])
    answers = f["answers"]

    def said(link_id):
        a = answers.get(link_id)
        return {"text": f"your answer on {(a['authored'] or '')[:10]}: {', '.join(a['labels'] or a['codes'] or [])}",
                "date": (a["authored"] or "")[:10]} if a else None

    if name.startswith("answer:"):
        link = name.split(":", 1)[1]
        codes = _answer(f, link)
        opts = {x["code"] for x in item["options"]}
        if codes and codes[0] in opts:
            return out(codes[0], said(link))
        return None
    if name == "bp_drug":
        bp = _answer(f, "blood-pressure")
        if bp and bp[0] in ("treated", "no", "untreated"):
            return out("yes" if bp[0] == "treated" else "no", said("blood-pressure"))
        return None
    if name == "lipid_drug":
        for link in ("lipid-medication",):
            c = _answer(f, link)
            if c:
                return out("yes" if c[0] in ("statin", "combination") else "no", said(link))
        return None
    if name == "tobacco":
        s = _answer(f, "smoking")
        if not s:
            return None
        if s[0] == "never":
            return out("never", said("smoking"))
        if s[0] == "current":
            return out("current", said("smoking"))
        quit_ = _answer(f, "tobacco-quit")
        if quit_:
            return out({"<1y": "quit-recent", "1-5y": "quit-1y", "5y+": "quit-5y"}[quit_[0]], said("tobacco-quit"))
        return None
    if name == "home_smoke":
        c = _answer(f, "tobacco-home")
        return out(c[0], said("tobacco-home")) if c else None
    if name == "family_diabetes":
        c = _answer(f, "family-diabetes")
        if c and c[0] == "yes":
            return out("close", said("family-diabetes"))
        return None  # "no" covers parents and siblings only; grandparents, aunts and cousins count too
    if name == "alcohol_none":
        c = _answer(f, "alcohol")
        return out("never", said("alcohol")) if c and c[0] == "none" else None
    if name == "wine_week":
        c = _answer(f, "alcohol")
        return out("no", said("alcohol")) if c and c[0] in ("none", "1-7") else None
    return None


# ── scoring (the page does the same in JavaScript) ───────────────────────────

def _points(item: dict, code: str) -> float | None:
    return next((x["points"] for x in item["options"] if x["code"] == code), None)


def enabled(item: dict, answers: dict[str, list[str]]) -> bool:
    cond = item.get("enableWhen")
    if not cond:
        return True
    for link, want in cond.items():
        wants = want if isinstance(want, list) else [want]
        if not set(answers.get(link) or []) & set(wants):
            return False
    return True


def band_of(protocol: dict, value: float, sex: str | None = None) -> tuple[int, str, str]:
    bands = protocol["bands"]
    if "cutOff" in protocol:
        cut = protocol["cutOff"].get((sex or "any").lower(), protocol["cutOff"]["any"])
        i = 1 if value >= cut else 0
        return i, bands[i][1], bands[i][2]
    i = max(k for k, b in enumerate(bands) if value >= b[0])
    return i, bands[i][1], bands[i][2]


def score(protocol: dict, answers: dict[str, list[str]], sex: str | None = None) -> dict | None:
    """The score so far, the range it can still reach, and its band once complete."""
    method = protocol.get("method")
    if method in (None, "family"):
        return family_summary(answers) if method == "family" else None
    items = [i for i in protocol["items"] if enabled(i, answers)]
    if method == "sum":
        got, lo, hi, missing = 0.0, 0.0, 0.0, []
        for it in items:
            skip = it.get("skipIf")
            if skip and all((answers.get(k) or [None])[0] == v for k, v in skip.items()):
                continue
            pts = [x["points"] for x in it["options"] if x["points"] is not None]
            code = (answers.get(it["linkId"]) or [None])[0]
            if code is not None:
                got += _points(it, code) or 0
            else:
                missing.append(it["linkId"])
                lo, hi = lo + min(pts), hi + max(pts)
        value = got
        result = {"value": value, "min": value + lo, "max": value + hi, "missing": missing,
                  "complete": not missing, "of": len(items)}
    elif method == "le8":
        metrics: dict[str, dict] = {}
        for it in items:
            m = metrics.setdefault(it["metric"], {"base": None, "adjust": 0, "items": []})
            code = (answers.get(it["linkId"]) or [None])[0]
            m["items"].append((it, code))
            if code is None:
                continue
            if it.get("adjust"):
                m["adjust"] += _points(it, code) or 0
            else:
                m["base"] = _points(it, code)
        per = {}
        for key, m in metrics.items():
            if m["base"] is None:
                continue
            per[key] = m["base"] if m["base"] == 0 else max(0, m["base"] + m["adjust"])
        missing = [k for k in metrics if k not in per]
        value = round(sum(per.values()) / len(per)) if per else None
        result = {"value": value, "metrics": per, "missing": missing, "complete": not missing,
                  "of": len(metrics), "note": "average of the metrics answered; diet (MEPA) is not scored here"}
        if value is not None:
            result["min"] = round(sum(per.values()) / len(metrics))
            result["max"] = round((sum(per.values()) + 100 * len(missing)) / len(metrics))
    else:
        return None
    if result.get("value") is not None and result["complete"]:
        i, label, meaning = band_of(protocol, result["value"], sex)
        result.update({"band": label, "bandIndex": i, "meaning": meaning,
                       "flag": _flagged(protocol, result["value"], i)})
        if protocol.get("bandSnomed"):
            result["snomed"] = protocol["bandSnomed"][i]
    return result


def _flagged(protocol: dict, value: float, band_index: int) -> bool:
    if "cutOff" in protocol:
        return band_index == 1
    if "flagFrom" in protocol:
        return value >= protocol["flagFrom"]
    if "flagBelow" in protocol:
        return value < protocol["flagBelow"]
    return False


def family_summary(answers: dict[str, list[str]]) -> dict | None:
    """The ESC 2021 reading of the family history: premature, later or none, with its SNOMED concept."""
    who = set(answers.get("family-cvd-who") or [])
    if not who:
        return None
    if who == {"none"}:
        return {"value": None, "complete": True, "band": "none", "meaning": "no heart disease in parents or siblings",
                "snomed": "160270001", "flag": False, "derived": {"family-cvd": "no"}}
    early = []
    if "father" in who and (answers.get("family-cvd-father-age") or [None])[0] == "<55":
        early.append("father before 55")
    if "mother" in who and (answers.get("family-cvd-mother-age") or [None])[0] == "<65":
        early.append("mother before 65")
    if who & {"brother", "sister"} and (answers.get("family-cvd-sibling-age") or [None])[0] == "yes":
        early.append("a brother or sister early")
    unknown = ("father" in who and (answers.get("family-cvd-father-age") or ["unknown"])[0] == "unknown") or \
              ("mother" in who and (answers.get("family-cvd-mother-age") or ["unknown"])[0] == "unknown") or \
              (who & {"brother", "sister"} and (answers.get("family-cvd-sibling-age") or ["unknown"])[0] == "unknown")
    if early:
        male = any(e.startswith(("father", "a brother")) for e in early)
        return {"value": None, "complete": True, "band": "premature", "flag": True,
                "meaning": "premature heart disease in the family (" + ", ".join(early) + "): an ESC 2021 risk modifier",
                "snomed": "439724007" if male else "438825005", "derived": {"family-cvd": "yes"}}
    if unknown or who == {"unknown"}:
        return {"value": None, "complete": False, "band": "age unknown", "flag": False,
                "meaning": "the age at the first event decides whether it counts", "snomed": "266894000"}
    return {"value": None, "complete": True, "band": "later in life", "flag": False,
            "meaning": "heart disease in the family, but not early: not a risk modifier in ESC 2021",
            "snomed": "266894000", "derived": {"family-cvd": "no"}}


# ── the personal plan ────────────────────────────────────────────────────────

def _findings(conn, today: str) -> list[dict]:
    try:
        from . import anamnesis
        return anamnesis.plan(conn, today=today)["findings"]
    except Exception:  # a store without the knowledge layer: no personal ranking, the protocols still work
        return []


def _finding_text(fd: dict) -> str:
    """'LDL cholesterol 4.4 mmol/L on 2026-09-04 above the guideline', or the finding's title."""
    v = (fd.get("values") or [None])[0]
    if v and v.get("value") is not None:
        rel = {"high": "above the guideline", "low": "below the guideline", "at_limit": "at the limit",
               "lab_high": "above the lab's limit"}.get(v.get("trigger"), "")
        return f"{v['name']} {v['value']:g} {v.get('unit') or ''} on {v['date']} {rel}".replace("  ", " ").strip()
    return fd["title"]


def plan(conn, today: str | None = None) -> dict:
    """The protocols prefilled from the person's data, ranked by their own findings, with the score so far."""
    today = today or dt.date.today().isoformat()
    f = facts(conn, today)
    sex = f["person"].get("sex")
    findings = _findings(conn, today)
    by_id = {fd["id"]: fd for fd in findings}
    done = {r["protocol"]: r for r in _rows(conn, RESPONSES)}
    out = []
    for p in PROTOCOLS:
        prior = {link: codes for link, a in f["answers"].items() if (codes := list(a["codes"] or []))}
        answers: dict[str, list[str]] = {}
        items = []
        for it in p["items"]:
            a = f["answers"].get(it["linkId"])
            if it.get("type") == "month":  # a month the person gave before: shown, not scored
                pre = {"code": None, "value": a["text"], "text": f"your answer on {(a['authored'] or '')[:10]}",
                       "observation": None, "date": (a["authored"] or "")[:10]} if a and a.get("text") else None
            else:
                pre = prefill_value(it["prefill"], p, it, f) if it.get("prefill") else None
            if pre is None and it["linkId"] in prior and any(x["code"] == prior[it["linkId"]][0] for x in it["options"]):
                pre = {"code": prior[it["linkId"]][0], "text": f"your answer on {(a['authored'] or '')[:10]}",
                       "observation": None, "date": (a["authored"] or "")[:10]}
            if pre and pre["code"] is not None:
                answers[it["linkId"]] = [pre["code"]]
            items.append({**{k: it.get(k) for k in ("linkId", "text", "loinc", "snomed", "type", "metric",
                                                   "enableWhen", "skipIf", "multiple")},
                          "options": it["options"], "prefilled": pre,
                          "prefillFrom": PREFILL.get(it.get("prefill") or "", None)})
        for it in items:
            it["enabled"] = enabled(it, answers)
        why = [_finding_text(by_id[r]) for r in p.get("raisedBy", []) if r in by_id]
        relevance = len(why) * 2 + sum(1 for i in items if i["prefilled"]) / max(1, len(items))
        if p["id"] == "tobacco" and "smoking" not in prior:
            relevance += 1
        if p["id"] == "lipid-therapy" and any(fd["id"] == "lipids" for fd in findings):
            relevance += 2
            why.append("whether a statin was taken changes how these lipid values read")
        if p["id"] == "findrisc" and f.get("glucose_ever_high", {}).get("value"):
            relevance += 2
            why.insert(0, f"{f['glucose_ever_high']['text']}: high blood glucose in FINDRISC (5 points)")
        last = done.get(p["id"])
        if last and last["authored"] and (dt.date.fromisoformat(today) -
                                          dt.date.fromisoformat(last["authored"][:10])).days <= 365:
            relevance -= 10  # answered this year: to the end, still there to review
        out.append({"id": p["id"], "name": p["name"], "title": p["title"], "kind": p["kind"], "year": p.get("year"),
                    "source": p.get("source"), "pmid": p.get("pmid"), "doi": p.get("doi"), "url": p.get("url"),
                    "licence": p.get("licence"), "loinc": p.get("loinc"), "snomed": p.get("snomed"),
                    "scoreSnomed": p.get("scoreSnomed"), "risks": p["risks"], "why": p["why"],
                    "critical": p.get("critical", []),
                    "evidence": [dict(EVIDENCE[e], id=e) for e in p.get("evidence", [])],
                    "forYou": list(dict.fromkeys(why))[:4], "relevance": round(relevance, 2),
                    "method": p.get("method"), "bands": p.get("bands"), "cutOff": p.get("cutOff"),
                    "flagFrom": p.get("flagFrom"), "flagBelow": p.get("flagBelow"), "bandSnomed": p.get("bandSnomed"),
                    "items": items, "prefilled": sum(1 for i in items if i["prefilled"]),
                    "score": score(p, answers, sex), "lastAnswered": last})
    out.sort(key=lambda x: -x["relevance"])
    treated = treated_values(conn, f)
    return {"asOf": today, "sex": sex, "birthYear": f["person"].get("birthYear"),
            "category": CATEGORY, "protocols": out, "treatedLipids": treated,
            "snomed": {c: {"display": d, "tag": t} for c, (d, t) in SNOMED.items()}}


LIPID_CODES = ["2093-3", "14647-2", "2089-1", "13457-7", "18262-6", "22748-8", "43396-1", "70204-3", "1884-6"]


def treated_values(conn, f: dict) -> list[dict]:
    """Lipid values measured while the person took cholesterol-lowering medicine, from the dates they gave."""
    med = _answer(f, "lipid-medication")
    start = (f["answers"].get("lipid-from") or {}).get("text")
    if not med or med[0] == "none" or not start:
        return []
    end = (f["answers"].get("lipid-until") or {}).get("text") if med[0] == "stopped" else None
    rows = _rows(conn, NEWEST, {"codes": LIPID_CODES})
    return [{"id": r["id"], "code": r["code"], "date": r["date"], "value": r["value"], "unit": r["unit"]}
            for r in rows if r["date"][:7] >= start[:7] and (end is None or r["date"][:7] <= end[:7])]


# ── seeding the category and storing answers ─────────────────────────────────

def _protocol_rows() -> list[dict]:
    rows = []
    for p in PROTOCOLS:
        rows.append({
            "id": p["id"], "name": p["name"], "title": p["title"], "kind": p["kind"], "year": p.get("year"),
            "source": p.get("source"), "pmid": p.get("pmid"), "doi": p.get("doi"), "url": p.get("url"),
            "licence": p.get("licence"), "why": p["why"], "critical": p.get("critical", []),
            "method": p.get("method") or "", "panelLoinc": p.get("loinc"), "scoreLoinc": p.get("scoreLoinc"),
            "snomed": p.get("snomed"), "scoreSnomed": p.get("scoreSnomed"), "risks": p["risks"],
            "bandFrom": [b[0] for b in p.get("bands", [])], "bandLabels": [b[1] for b in p.get("bands", [])],
            "bandMeanings": [b[2] for b in p.get("bands", [])],
            "codes": [c for c in (p.get("loinc"), p.get("scoreLoinc")) if c],
            "snomedCodes": [c for c in (p.get("snomed"), p.get("scoreSnomed")) if c] + list(p.get("bandSnomed", [])),
            "items": [{
                "id": f"{p['id']}|{i['linkId']}", "linkId": i["linkId"], "order": n, "text": i["text"],
                "type": i.get("type", "choice"), "multiple": bool(i.get("multiple")), "loinc": i.get("loinc"),
                "snomed": i.get("snomed"), "metric": i.get("metric"),
                "prefill": PREFILL.get(i.get("prefill") or "") or (
                    "your earlier answer" if (i.get("prefill") or "").startswith("answer:") else None),
                "enableWhen": json.dumps(i["enableWhen"], sort_keys=True) if i.get("enableWhen") else None,
                "options": [x["code"] for x in i["options"]], "labels": [x["label"] for x in i["options"]],
                "points": [x["points"] if x["points"] is not None else 0 for x in i["options"]],
                "optionSnomed": [x["snomed"] or "" for x in i["options"]],
                "optionLoinc": [x["la"] or "" for x in i["options"]],
                "answerCodes": [{"option": x["code"], "snomed": x["snomed"]} for x in i["options"] if x["snomed"]],
            } for n, i in enumerate(p["items"], 1)],
        })
    return rows


SEED_CATEGORY = """
MERGE (cat:AnamnesisCategory {id: $category.id})
SET cat.name = $category.name, cat.description = $category.description, cat.version = $version
WITH cat
UNWIND $snomed AS s
MERGE (c:SnomedCode {code: s.code})
SET c.display = s.display, c.semanticTag = s.tag, c.system = 'http://snomed.info/sct'
RETURN count(*) AS codes
"""

SEED_PROTOCOLS = """
MATCH (cat:AnamnesisCategory {id: $categoryId})
UNWIND $protocols AS p
MERGE (q:AnamnesisProtocol {id: p.id})
SET q.name = p.name, q.title = p.title, q.kind = p.kind, q.year = p.year, q.source = p.source, q.pmid = p.pmid,
    q.doi = p.doi, q.url = p.url, q.licence = p.licence, q.why = p.why, q.critical = p.critical,
    q.method = p.method, q.panelLoinc = p.panelLoinc, q.scoreLoinc = p.scoreLoinc, q.snomed = p.snomed,
    q.scoreSnomed = p.scoreSnomed, q.bandFrom = p.bandFrom, q.bandLabels = p.bandLabels,
    q.bandMeanings = p.bandMeanings
MERGE (cat)-[:HAS_PROTOCOL]->(q)
WITH q, p
OPTIONAL MATCH (q)-[old:INFORMS|CODED_BY]->()
DELETE old
WITH DISTINCT q, p
UNWIND p.risks AS riskId
MATCH (h:HealthRisk {id: riskId})
MERGE (q)-[:INFORMS]->(h)
RETURN count(*) AS links
"""

SEED_PROTOCOL_LOINC = """
UNWIND $protocols AS p
MATCH (q:AnamnesisProtocol {id: p.id})
UNWIND p.codes AS code
MERGE (c:LoincCode {code: code})
MERGE (q)-[:CODED_BY]->(c)
RETURN count(*) AS links
"""

SEED_PROTOCOL_SNOMED = """
UNWIND $protocols AS p
MATCH (q:AnamnesisProtocol {id: p.id})
UNWIND p.snomedCodes AS code
MATCH (s:SnomedCode {code: code})
MERGE (q)-[:CODED_BY]->(s)
RETURN count(*) AS links
"""

SEED_ITEMS = """
UNWIND $protocols AS p
MATCH (q:AnamnesisProtocol {id: p.id})
UNWIND p.items AS it
MERGE (i:ProtocolItem {id: it.id})
SET i.linkId = it.linkId, i.order = it.order, i.text = it.text, i.type = it.type, i.multiple = it.multiple,
    i.loinc = it.loinc, i.snomed = it.snomed, i.metric = it.metric, i.prefill = it.prefill,
    i.enableWhen = it.enableWhen, i.options = it.options, i.labels = it.labels, i.points = it.points,
    i.optionSnomed = it.optionSnomed, i.optionLoinc = it.optionLoinc, i.protocol = p.id
MERGE (q)-[:HAS_ITEM]->(i)
WITH i, it
OPTIONAL MATCH (i)-[old:CODED_BY|ANSWER_CODE]->()
DELETE old
WITH DISTINCT i, it
UNWIND it.answerCodes AS ac
MATCH (s:SnomedCode {code: ac.snomed})
MERGE (i)-[:ANSWER_CODE {option: ac.option}]->(s)
RETURN count(*) AS links
"""

def _snomed_rows() -> list[dict]:
    return [{"code": c, "display": d, "tag": t} for c, (d, t) in SNOMED.items()]


def version() -> str:
    """A fingerprint of everything seeded: a store with it is current."""
    blob = json.dumps([CATEGORY, _snomed_rows(), _protocol_rows()], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def swift_data() -> dict:
    """What the Swift library needs: the rows it seeds and the definitions it checks and scores answers with."""
    return {"category": CATEGORY, "version": version(), "snomed": _snomed_rows(), "rows": _protocol_rows(),
            "protocols": PROTOCOLS}


def seed(conn) -> dict[str, int]:
    rows = _protocol_rows()
    codes = conn.execute(SEED_CATEGORY, {"category": CATEGORY, "snomed": _snomed_rows(),
                                         "version": version()}).single()["codes"]
    links = conn.execute(SEED_PROTOCOLS, {"categoryId": CATEGORY["id"], "protocols": rows}).single()
    conn.execute(SEED_PROTOCOL_LOINC, {"protocols": rows})
    conn.execute(SEED_PROTOCOL_SNOMED, {"protocols": rows})
    items = conn.execute(SEED_ITEMS, {"protocols": rows}).single()
    item_rows = [i for p in rows for i in p["items"]]
    conn.execute(SEED_ITEM_LOINC, {"items": [i for i in item_rows if i["loinc"]]})
    conn.execute(SEED_ITEM_SNOMED, {"items": [i for i in item_rows if i["snomed"]]})
    return {"protocols": len(rows), "items": len(item_rows), "snomedCodes": codes,
            "riskLinks": links["links"] if links else 0, "answerCodes": items["links"] if items else 0}


SEED_ITEM_LOINC = """
UNWIND $items AS it
MATCH (i:ProtocolItem {id: it.id})
MERGE (c:LoincCode {code: it.loinc})
MERGE (i)-[:CODED_BY]->(c)
RETURN count(*) AS links
"""

SEED_ITEM_SNOMED = """
UNWIND $items AS it
MATCH (i:ProtocolItem {id: it.id}), (s:SnomedCode {code: it.snomed})
MERGE (i)-[:CODED_BY]->(s)
RETURN count(*) AS links
"""

STORE_RESPONSE = """
MATCH (p:Patient {id: $patientId})
MATCH (q:AnamnesisProtocol {id: $protocol})
MERGE (r:QuestionnaireResponse {id: $responseId})
SET r.authored = $authored, r.status = $status, r.source = $source, r.protocol = $protocol,
    r.score = $score, r.band = $band, r.meaning = $meaning, r.flag = $flag
MERGE (p)-[:HAS_RESPONSE]->(r)
MERGE (r)-[:RESPONDS_TO]->(q)
WITH r
UNWIND $answers AS a
MATCH (i:ProtocolItem {id: $protocol + '|' + a.linkId})
MERGE (ans:Answer {id: $responseId + '|' + a.linkId})
SET ans.linkId = a.linkId, ans.question = a.question, ans.codes = a.codes, ans.labels = a.labels, ans.text = a.text,
    ans.snomed = a.snomed, ans.points = a.points, ans.riskFactor = a.riskFactor, ans.authored = $authored,
    ans.prefilled = a.prefilled, ans.protocol = $protocol
MERGE (r)-[:HAS_ANSWER]->(ans)
MERGE (ans)-[:ANSWERS]->(i)
RETURN count(*) AS answers
"""

STORE_ANSWER_CODES = """
UNWIND $rows AS row
MATCH (ans:Answer {id: $responseId + '|' + row.linkId})
UNWIND row.snomed AS code
MATCH (s:SnomedCode {code: code})
MERGE (ans)-[:CODED_BY]->(s)
RETURN count(*) AS links
"""

STORE_PREFILLED_FROM = """
UNWIND $rows AS row
MATCH (ans:Answer {id: $responseId + '|' + row.linkId}), (o:Observation {resourceId: row.observation})
MERGE (ans)-[:PREFILLED_FROM]->(o)
RETURN count(*) AS links
"""

STORE_RESPONSE_LINKS = """
MATCH (r:QuestionnaireResponse {id: $responseId})
UNWIND $snomed AS code
MATCH (s:SnomedCode {code: code})
MERGE (r)-[:CODED_BY]->(s)
WITH DISTINCT r
UNWIND $risks AS riskId
MATCH (h:HealthRisk {id: riskId})
MERGE (r)-[:RISK_FACTOR_FOR]->(h)
RETURN count(*) AS links
"""

# A derived answer the data-driven anamnesis reads (family-cvd from the family history).
STORE_DERIVED = """
MATCH (r:QuestionnaireResponse {id: $responseId})
UNWIND $rows AS row
MERGE (ans:Answer {id: $responseId + '|' + row.linkId})
SET ans.linkId = row.linkId, ans.codes = row.codes, ans.labels = row.labels, ans.authored = $authored,
    ans.riskFactor = row.riskFactor, ans.derivedFrom = $protocol, ans.question = row.question
MERGE (r)-[:HAS_ANSWER]->(ans)
RETURN count(*) AS answers
"""


def normalise(protocol_id: str, answers: dict) -> list[dict]:
    """{linkId: code | [codes] | {"codes", "text", "prefilled", "observation"}} -> rows; unknown codes are refused."""
    p = PROTOCOL.get(protocol_id)
    if p is None:
        raise ValueError(f"unknown protocol {protocol_id!r}; known: {', '.join(PROTOCOL)}")
    rows = []
    for link_id, value in answers.items():
        item = ITEM.get((protocol_id, link_id))
        if item is None:
            raise ValueError(f"{protocol_id}: unknown question {link_id!r}")
        text, prefilled, observation = None, None, None
        if isinstance(value, dict):
            codes, text = value.get("codes") or [], value.get("text")
            prefilled, observation = value.get("prefilled"), value.get("observation")
        else:
            codes = [value] if isinstance(value, str) else list(value)
        if item.get("type") == "month":
            month = text or (codes[0] if codes else "")
            try:
                dt.date.fromisoformat(f"{month[:7]}-01")
            except ValueError:
                raise ValueError(f"{link_id}: {month!r} is not a year and month (YYYY-MM)") from None
            rows.append({"linkId": link_id, "codes": [], "labels": [], "text": month[:7], "snomed": [], "points": None,
                         "riskFactor": False, "question": item["text"], "prefilled": prefilled, "observation": observation})
            continue
        options = {x["code"]: x for x in item["options"]}
        bad = [c for c in codes if c not in options]
        if bad:
            raise ValueError(f"{link_id}: {bad} not among {list(options)}")
        if len(codes) > 1 and not item.get("multiple"):
            raise ValueError(f"{link_id} takes one answer, got {codes}")
        if not codes and not text:
            continue
        chosen = [options[c] for c in codes]
        rows.append({"linkId": link_id, "codes": codes, "labels": [x["label"] for x in chosen], "text": text,
                     "snomed": [x["snomed"] for x in chosen if x["snomed"]],
                     "points": sum(x["points"] for x in chosen if x["points"] is not None) if any(
                         x["points"] is not None for x in chosen) else None,
                     "riskFactor": any(x["riskFactor"] for x in chosen), "question": item["text"],
                     "prefilled": prefilled, "observation": observation})
    return rows


def store_response(conn, patient_id: str, protocol_id: str, answers: dict, source: str = "page",
                   authored: str | None = None, sex: str | None = None) -> dict:
    authored = authored or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = normalise(protocol_id, answers)
    p = PROTOCOL[protocol_id]
    seed(conn)
    if sex is None:
        sex = ((_rows(conn, PERSON) or [{}])[0]).get("sex")
    codes = {r["linkId"]: r["codes"] for r in rows if r["codes"]}
    result = score(p, codes, sex) or {}
    response_id = f"{patient_id}|{protocol_id}|{authored}"
    conn.execute(STORE_RESPONSE, {
        "patientId": patient_id, "protocol": protocol_id, "responseId": response_id, "authored": authored,
        "status": "completed" if result.get("complete", True) else "in-progress", "source": source,
        "score": result.get("value"), "band": result.get("band"), "meaning": result.get("meaning"),
        "flag": bool(result.get("flag")), "answers": rows})
    conn.execute(STORE_ANSWER_CODES, {"responseId": response_id, "rows": [r for r in rows if r["snomed"]]})
    pre = [r for r in rows if r.get("observation")]
    if pre:
        conn.execute(STORE_PREFILLED_FROM, {"responseId": response_id, "rows": pre})
    response_codes = [c for c in (p.get("scoreSnomed"), result.get("snomed")) if c]
    conn.execute(STORE_RESPONSE_LINKS, {"responseId": response_id, "snomed": response_codes,
                                        "risks": p["risks"] if result.get("flag") else []})
    derived = []
    for link, code in (result.get("derived") or {}).items():
        derived.append({"linkId": link, "codes": [code], "labels": ["Yes" if code == "yes" else "No"],
                        "riskFactor": code == "yes", "question": "Did a parent or sibling have heart disease early "
                                                                 "(men before 55, women before 65)?"})
    if derived:
        conn.execute(STORE_DERIVED, {"responseId": response_id, "rows": derived, "authored": authored,
                                     "protocol": protocol_id})
    return {"answers": len(rows), "score": result.get("value"), "band": result.get("band"),
            "flag": bool(result.get("flag")), "derived": len(derived), "prefilledFrom": len(pre)}
