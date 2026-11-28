"""German guidelines and appraised studies: which guideline applies, and how good the evidence is.

Extends the knowledge layer (knowledge.py) with

    (:Study {kind: 'guideline', publisher, register, guidelineClass, version,
             adoptedDate, validUntil, earliestValidUntil, validity,
             referencesCount, evidenceMedianAge, newestCitedYear, currency})
        the six German guidelines the MinimumViableHealthDataspacev2 pipeline reads from
        open sources (NVL from leitlinien.de, DEGAM from degam.de): metadata and the
        reference list only, never guideline text (the publishers' imprints require
        written consent to store it in electronic systems)
    (:Study {publicationStatus, statusCheckedAt,
             appraisalQuestion, appraisalVerdict, certainty,
             appraisalChecked, appraisalOpen, appraisedAt, appraisalSource})
        a study checked for retraction, correction and expression of concern
        (PubMed, with a known retracted paper as positive control) and appraised
        for one question: facts checked by code, checklist items with a quote,
        judgement items left open for a person (Woelfle et al., J Clin Epidemiol 2024)
    (:Study)-[:CITES {source: 'reference list'}]->(:Study)
        a German guideline cites a study in this graph (its printed reference list)
    (:Study {gatePassed, gateReasons})-[:AFTER_CUTOFF_OF {topic, summary}]->(:Study {kind: 'guideline'})
        published after the guideline was adopted, about one of its recommendations, and
        through the quality gate (gate() below): flagged, never applied in the
        guideline's place
    (:Study)-[:DISAGREES_WITH {topic, summary}]->(:Study)
        two guidelines, or a guideline and its dissenting societies, answer one
        question differently: show both, never pick one silently

Not medical advice: the appraisals say how far a study can answer a question,
not what a person should do.
"""
from __future__ import annotations

LDL = ["22748-8", "13457-7", "18262-6", "2089-1"]
APOB = ["1884-6"]
LPA = ["10835-7"]
BP = ["8480-6", "8462-4"]
HBA1C = ["4548-4", "59261-8"]
EGFR = ["62238-1", "98979-8", "33914-3", "48642-3"]
UACR = ["9318-7", "14959-1"]

DRAFT = ("https://github.com/ma3u/MinimumViableHealthDataspacev2/blob/claude/study-evaluation-master-prompt-vtyy9t/"
         "docs/discussions/study-appraisal-for-lay-people.md")
PIPELINE = "https://github.com/ma3u/MinimumViableHealthDataspacev2/pull/1159"
CHECKED = "2026-11-20"

# ── the six German guidelines (metadata and reference list, as of 2026-11-19) ──
GUIDELINES = [
    {"id": "degam-053-024", "year": 2025, "design": "clinical practice guideline (S3, DEGAM)",
     "citation": "DEGAM S3-Leitlinie 053-024, Version 2.3 (2025)",
     "title": "Hausärztliche Risikoberatung zur kardiovaskulären Prävention",
     "url": "https://www.degam.de/leitlinie-s3-053-024", "pmid": None,
     "publisher": "DEGAM", "register": "AWMF 053-024", "guidelineClass": "S3", "version": "2.3",
     "adoptedDate": "2025-08-01", "validUntil": "2029-11-30", "earliestValidUntil": "2029-11-30",
     "validity": "active", "referencesCount": 255, "evidenceMedianAge": 7, "newestCitedYear": 2024,
     "currency": [
         "Lipoprotein(a): advises against routine measurement on one 2012 meta-analysis (ERFC, c-statistic "
         "+0.0016, retrieved September 2023); its search update found nothing newer. Six societies (DGK, DGIM, "
         "DDG, DHL, DGSP, DGPR) dissent and favour one measurement in adulthood.",
         "Not cited although published before adoption: EPIC-Norfolk 2025 (Lp(a), LDL and hsCRP once, 20 years).",
         "After adoption and through the quality gate: CTT 2026 (statin side effects in product labels), "
         "Lp(a)HORIZON 2026 (lowering Lp(a) with pelacarsen did not reduce events). Context only, below the gate: "
         "WHS 2026 (thresholds chosen after the data) and the Tel Aviv cohort 2026 (retrospective).",
         "Statins as a fixed moderate dose by absolute risk; the ESC/EAS 2025 update sets LDL targets instead.",
     ],
     "examines": LDL + APOB + LPA + BP + EGFR + UACR, "informs": ["score2"],
     "topics": ["Heart and vessels"]},
    {"id": "degam-053-048", "year": 2024, "design": "clinical practice guideline (S3, DEGAM)",
     "citation": "DEGAM S3-Leitlinie 053-048, Version 2.0 (2024)",
     "title": "Versorgung von Patient*innen mit chronischer, nicht-nierenersatztherapiepflichtiger "
              "Nierenkrankheit in der Hausarztpraxis",
     "url": "https://www.degam.de/leitlinie-s3-053-048", "pmid": None,
     "publisher": "DEGAM", "register": "AWMF 053-048", "guidelineClass": "S3", "version": "2.0",
     "adoptedDate": "2024-11-01", "validUntil": "2029-06-30", "earliestValidUntil": "2029-06-30",
     "validity": "active", "referencesCount": 250, "evidenceMedianAge": 7, "newestCitedYear": 2024,
     "currency": [],
     "examines": EGFR + UACR + ["2160-0"], "informs": ["egfr"], "topics": ["Kidney"]},
    {"id": "nvl-hypertonie-1", "year": 2023, "design": "clinical practice guideline (S3, Nationale VersorgungsLeitlinie)",
     "citation": "Nationale VersorgungsLeitlinie Hypertonie, Version 1.0 (2023)",
     "title": "Nationale VersorgungsLeitlinie Hypertonie",
     "url": "https://doi.org/10.6101/AZQ/000502", "pmid": None, "page": "https://www.leitlinien.de/themen/hypertonie",
     "publisher": "NVL (BÄK, KBV, AWMF)", "register": "NVL 009", "guidelineClass": "S3", "version": "1.0",
     "adoptedDate": "2023-06-29", "validUntil": "2028-06-29", "earliestValidUntil": "2028-06-29",
     "validity": "active", "referencesCount": 182, "evidenceMedianAge": 6, "newestCitedYear": 2023,
     "currency": ["Cites the Hygia Chronotherapy Trial, which carries an expression of concern (no recommendation "
                  "is derived from it)."],
     "examines": BP + EGFR + UACR, "informs": [], "topics": ["Heart and vessels", "Kidney"]},
    {"id": "nvl-diabetes-3", "year": 2023, "design": "clinical practice guideline (S3, Nationale VersorgungsLeitlinie)",
     "citation": "Nationale VersorgungsLeitlinie Typ-2-Diabetes, Version 3.0 (2023)",
     "title": "Nationale VersorgungsLeitlinie Typ-2-Diabetes",
     "url": "https://doi.org/10.6101/AZQ/000503", "pmid": None, "page": "https://www.leitlinien.de/themen/diabetes",
     "publisher": "NVL (BÄK, KBV, AWMF)", "register": "NVL 001", "guidelineClass": "S3", "version": "3.0",
     "adoptedDate": "2023-05-15", "validUntil": "2028-05-15", "earliestValidUntil": "2028-05-15",
     "validity": "active", "referencesCount": 228, "evidenceMedianAge": 5, "newestCitedYear": 2023,
     "currency": ["FLOW (semaglutide in diabetes with kidney disease, NEJM 2024) came a year after adoption."],
     "examines": HBA1C + ["2345-7", "1558-6"] + EGFR + UACR, "informs": [], "topics": ["Metabolism"]},
    {"id": "nvl-khk-7", "year": 2024, "design": "clinical practice guideline (S3, Nationale VersorgungsLeitlinie)",
     "citation": "Nationale VersorgungsLeitlinie Chronische KHK, Version 7.0 (2024)",
     "title": "Nationale VersorgungsLeitlinie Chronische KHK",
     "url": "https://doi.org/10.6101/AZQ/000514", "pmid": None, "page": "https://www.leitlinien.de/themen/khk",
     "publisher": "NVL (BÄK, KBV, AWMF)", "register": "NVL 004", "guidelineClass": "S3", "version": "7.0",
     "adoptedDate": "2024-08-15", "validUntil": "2029-08-14", "earliestValidUntil": "2029-08-14",
     "validity": "active", "referencesCount": 389, "evidenceMedianAge": 11, "newestCitedYear": 2024,
     "currency": ["For people with coronary heart disease, not for primary prevention."],
     "examines": LDL + LPA + BP, "informs": [], "topics": ["Heart and vessels"]},
    {"id": "nvl-herzinsuffizienz-4", "year": 2023,
     "design": "clinical practice guideline (S3, Nationale VersorgungsLeitlinie)",
     "citation": "Nationale VersorgungsLeitlinie Chronische Herzinsuffizienz, Version 4.0 (2023)",
     "title": "Nationale VersorgungsLeitlinie Chronische Herzinsuffizienz",
     "url": "https://doi.org/10.6101/AZQ/000510", "pmid": None, "page": "https://www.leitlinien.de/themen/herzinsuffizienz",
     "publisher": "NVL (BÄK, KBV, AWMF)", "register": "NVL 006", "guidelineClass": "S3", "version": "4.0",
     "adoptedDate": "2023-12-12", "validUntil": "2028-12-12", "earliestValidUntil": "2024-10-22",
     "validity": "partly-expired", "referencesCount": 628, "evidenceMedianAge": 9, "newestCitedYear": 2023,
     "currency": ["Only the chapter on drug therapy was renewed in 2023; all other chapters are from 2019 and "
                  "expired on 2024-10-22."],
     "examines": ["33762-6"], "informs": [], "topics": ["Heart and vessels"]},
    # Another country's guideline, consulted only for a stated reason (QUESTIONS below). Read through
    # Helsedirektoratet's open API (norway.py); NLOD allows storing its text, but the reader keeps the
    # same facts as for the German boxes until a person has checked the API's fields.
    {"id": "hdir-hjerte-kar", "year": 2017, "design": "national clinical guideline (Helsedirektoratet, GRADE)",
     "citation": "Helsedirektoratet, Nasjonal faglig retningslinje for forebygging av hjerte- og karsykdom "
                 "(2017, last professional change 2024-12-05)",
     "title": "Nasjonal faglig retningslinje for forebygging av hjerte- og karsykdom",
     "url": "https://www.helsedirektoratet.no/retningslinjer/forebygging-av-hjerte-og-karsykdom", "pmid": None,
     "publisher": "Helsedirektoratet (Norway)", "register": "HDIR hjerte-kar",
     "guidelineClass": "national clinical guideline", "version": "2024-12-05",
     "adoptedDate": None, "validUntil": None, "earliestValidUntil": None, "validity": "active",
     "referencesCount": None, "evidenceMedianAge": None, "newestCitedYear": None,
     "currency": ["Statins in primary prevention last changed on 2024-12-05; risk assessment, targets and "
                  "secondary prevention are unchanged since 2018-03-05.",
                  "Estimates risk with NORRISK 2, calibrated for Norway, not with SCORE2: its treatment "
                  "thresholds do not apply to a SCORE2 result."],
     "country": "NO", "language": "nb", "interface": "api", "riskModel": "NORRISK 2",
     "licence": "NLOD 2.0 and the HAPI terms of use", "licenceClass": "open",
     "examines": LDL + LPA, "informs": [], "topics": ["Heart and vessels"]},
]

# Where a guideline comes from and what its licence lets the graph keep (issue #23). licenceClass:
# open (the text may be stored), quote-with-attribution, non-commercial, permission (facts and link only).
for _g in GUIDELINES:
    _g.setdefault("country", "DE")
    _g.setdefault("language", "de")
    _g.setdefault("interface", "pdf")
    _g.setdefault("riskModel", "SCORE2" if _g["id"] == "degam-053-024" else None)
    _g.setdefault("licence", "Publisher's imprint: storing the text needs written consent")
    _g.setdefault("licenceClass", "permission")

# ── appraised studies: example 1, LDL and ApoB without a statin ─────────────
# Appraised in full on 2026-11-19 (DRAFT, tests 1 to 3); status rechecked in PubMed on CHECKED.
STUDIES = [
    {"id": "keto-cta-2025", "year": 2025, "design": "observational cohort, 100 people, one year, no comparison group",
     "citation": "KETO-CTA, Soto-Mota et al., JACC Adv 2025;4:101686, retracted",
     "title": "Longitudinal Data From the KETO-CTA Study: Plaque Predicts Plaque, ApoB Does Not",
     "url": "https://doi.org/10.1016/j.jacadv.2025.101686", "pmid": "40192608",
     "publicationStatus": "retracted", "statusCheckedAt": CHECKED,
     "appraisalQuestion": "Is a high LDL on a low-carb diet harmless?",
     "appraisalVerdict": "Retracted on 2026-03-11; it could not answer the question before either: no comparison "
                         "group, one year, a plaque change of the size of the difference between two readers, "
                         "registered after the start. A retraction does not prove the opposite.",
     "certainty": "none (retracted)",
     "appraisalChecked": ["Retraction and expression of concern (PubMed)", "Registered after the first patient "
                          "(ClinicalTrials.gov history)", "Registered outcome reported only after a letter"],
     "appraisalOpen": ["Weight of the undisclosed equity and the funder's role", "Whether the re-analysis preprint "
                       "changes anything (not peer reviewed)"],
     "appraisedAt": "2026-11-19", "appraisalSource": DRAFT,
     "examines": LDL + APOB, "informs": [], "topics": ["Heart and vessels"]},
    {"id": "ctt-2026-labels", "year": 2026,
     "design": "individual-participant meta-analysis, 19 placebo-controlled statin trials, 123,940 people",
     "citation": "CTT Collaboration, Lancet 2026;407:689",
     "title": "Assessment of adverse effects attributed to statin therapy in product labels",
     "url": "https://doi.org/10.1016/S0140-6736(25)01578-8", "pmid": "41655587",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED,
     "appraisalQuestion": "I stopped a statin after three months. Were my side effects real?",
     "appraisalVerdict": "For sleep, memory, mood and sexual function the trials show no excess, with tight "
                         "intervals; liver test changes are real, early and dose-dependent. Muscle symptoms (2022 "
                         "paper of the group): about 1 in 15 caused by the statin in year one. Whether symptoms that "
                         "make people stop are caused by the drug was not measured.",
     "certainty": "moderate",
     "appraisalChecked": ["No retraction, correction or concern (PubMed, Crossref)", "Double-blind trials only",
                          "False discovery rate controlled over 66 outcomes"],
     "appraisalOpen": ["A third of participants were in trials that did not record ordinary complaints",
                       "Run-in periods may have removed people who did not tolerate the drug",
                       "Data not released; the reviewers are the trialists"],
     "appraisedAt": "2026-11-19", "appraisalSource": DRAFT,
     "examines": LDL, "informs": [], "topics": ["Heart and vessels"]},
    {"id": "ccc-smoking-2025", "year": 2025, "design": "pooled analysis of 22 prospective cohorts, 323,826 adults",
     "citation": "Tasdighi et al., PLoS Med 2025;22:e1004561",
     "title": "Association between cigarette smoking status, intensity, and cessation duration with long-term "
              "cardiovascular outcomes",
     "url": "https://doi.org/10.1371/journal.pmed.1004561", "pmid": "41252354",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED,
     "appraisalQuestion": "I only smoke occasionally. Does that count?",
     "appraisalVerdict": "One cigarette a day or fewer: cardiovascular disease HR 1.47 (1.28 to 1.70) against "
                         "never-smokers, in 1,423 people, mostly older American women. After little lifetime "
                         "exposure and stopping, no excess is visible.",
     "certainty": "moderate for the direction, low for the size",
     "appraisalChecked": ["No retraction, correction or concern (PubMed, Crossref)", "Three different totals in "
                          "the paper", "Hazard ratio appears only after adjustment (0.83 crude, 1.51 adjusted)"],
     "appraisalOpen": ["Residual confounding", "Whether data from older women apply to a man of 45 to 55"],
     "appraisedAt": "2026-11-19", "appraisalSource": DRAFT,
     "examines": [], "informs": ["score2"], "topics": ["Heart and vessels"]},
]

# ── example 2, lipoprotein(a): appraised on CHECKED ─────────────────────────
LPA = "https://github.com/ma3u/relate-hackathon-team/blob/main/docs/evidence/lpa-appraisal-2026-11-20.md"
LPA_QUESTION = ("Does an Lp(a) of about 30 mg/dL raise the risk of an adult without heart disease, and does "
                "lowering Lp(a) help?")
LPA_STUDIES = [
    {"id": "lpa-horizon-2026", "year": 2026,
     "design": "randomised placebo-controlled trial, 8,323 people with cardiovascular disease and Lp(a) of at least "
               "70 mg/dL, median 4.7 years",
     "citation": "Lp(a)HORIZON, Cho et al., N Engl J Med 2026",
     "title": "Pelacarsen and Cardiovascular Outcomes in Patients with High Lipoprotein(a)",
     "url": "https://doi.org/10.1056/NEJMoa2610159", "pmid": "43001734",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": LPA_QUESTION,
     "appraisalVerdict": "Pelacarsen lowered Lp(a) by about 70% and did not reduce heart attacks, strokes or "
                         "cardiovascular deaths: HR 1.02 (0.90 to 1.15). The first outcome trial of Lp(a) lowering "
                         "is null. It enrolled people who already had cardiovascular disease and far higher Lp(a), "
                         "so it says nothing direct about a value of 30 mg/dL.",
     "certainty": "high for this drug in its trial population; very low for any benefit at 30 mg/dL",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Registered primary outcomes "
                          "(NCT04023552) match the reported ones", "PubMed has not yet typed it as a randomised "
                          "trial: the type comes from indexing, which lags"],
     "appraisalOpen": ["Full text not read (subscription)", "Registry history not read (HTTP 403)",
                       "Funded by the maker of the drug"],
     "appraisedAt": CHECKED, "appraisalSource": LPA,
     "examines": ["10835-7"], "informs": [], "topics": ["Heart and vessels"]},
    {"id": "epic-norfolk-lpa-2025", "year": 2025,
     "design": "prospective cohort, 17,087 European adults without cardiovascular disease, 20 years",
     "citation": "EPIC-Norfolk, Kraaijenhof et al., Eur Heart J 2025;46:3875",
     "title": "Low-density lipoprotein cholesterol, C-reactive protein, and lipoprotein(a) universal one-time "
              "screening in primary prevention: the EPIC-Norfolk study",
     "url": "https://doi.org/10.1093/eurheartj/ehaf209", "pmid": "40167249",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": LPA_QUESTION,
     "appraisalVerdict": "The closest match: European men and women without heart disease, Lp(a) in mg/dL. 30 mg/dL "
                         "lies in the fourth fifth (16 to under 36), with no detectable extra risk: HR 0.97 (0.87 "
                         "to 1.09), men 1.05 (0.90 to 1.22). Only the top fifth (36 and above) carried more, HR "
                         "1.19; LDL cholesterol carried more than Lp(a) in the same model (HR 1.78).",
     "certainty": "low for a meaningful increase at 30 mg/dL",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Read in full", "Not preregistered",
                          "17,087 in most places, 17,078 once"],
     "appraisalOpen": ["Calls for universal screening without a discrimination statistic",
                       "Industry ties of several authors", "Lp(a) measured once"],
     "appraisedAt": CHECKED, "appraisalSource": LPA,
     "examines": ["10835-7"] + LDL + ["30522-7"], "informs": [], "topics": ["Heart and vessels"]},
    {"id": "whs-lpa-2026", "year": 2026, "design": "prospective cohort, 27,748 US women, 30 years",
     "citation": "Women's Health Study, Nordestgaard et al., JAMA Cardiol 2026;11:175",
     "title": "Thirty-Year Risk of Cardiovascular Disease Among Healthy Women According to Clinical Thresholds of "
              "Lipoprotein(a)",
     "url": "https://doi.org/10.1001/jamacardio.2025.5043", "pmid": "41499112",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": LPA_QUESTION,
     "appraisalVerdict": "Above 30 mg/dL somewhat higher 30-year risk of heart events in women; stroke and "
                         "cardiovascular death only above 120 mg/dL. The hypothesis was formulated after the data "
                         "were collected, and many cut-offs were tried.",
     "certainty": "low (women only, post hoc thresholds)",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Hypothesis stated as post hoc"],
     "appraisalOpen": ["Full text under embargo: the hazard ratio for 30 to 50 mg/dL not seen",
                       "A co-author receives royalties on an LPA variant patent", "Whether it applies to men"],
     "appraisedAt": CHECKED, "appraisalSource": LPA,
     "examines": ["10835-7"], "informs": [], "topics": ["Heart and vessels"]},
    {"id": "telaviv-lpa-2026", "year": 2026,
     "design": "retrospective single-centre cohort, 3,052 adults in a screening programme, median 6.4 years",
     "citation": "Tel Aviv cohort, Golan et al., Clin Res Cardiol 2026;115:357",
     "title": "Prognostic value of lipoprotein(a) in a primary prevention ambulatory cohort",
     "url": "https://doi.org/10.1007/s00392-025-02826-x", "pmid": "41400669",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": LPA_QUESTION,
     "appraisalVerdict": "Risk bends upward at about 50 mg/dL (48 without heart disease); above 50, HR 1.55 (1.10 "
                         "to 2.17). The threshold was found and tested in the same data. 30 mg/dL lies below it.",
     "certainty": "very low for this person",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Abstract only (subscription)"],
     "appraisalOpen": ["Selected screening population outside Europe", "Threshold found and tested on one data set"],
     "appraisedAt": CHECKED, "appraisalSource": LPA,
     "examines": ["10835-7"], "informs": ["score2"], "topics": ["Heart and vessels"]},
]

# ── example 3, a statin that makes a person tired: appraised on CHECKED ──────
STATIN = ("https://github.com/ma3u/relate-hackathon-team/blob/main/docs/evidence/"
          "statin-tolerance-appraisal-2026-11-20.md")
STATIN_QUESTION = ("A statin makes me tired. Is it the statin, does coenzyme Q10 help, and what else lowers "
                   "LDL if I cannot take one?")
STATIN_STUDIES = [
    {"id": "samson-2020", "year": 2020,
     "design": "randomised n-of-1 trial, 60 people who had stopped a statin, 12 months of statin, placebo or "
               "nothing in random order",
     "citation": "SAMSON, Wood et al., N Engl J Med 2020;383:2182 (letter)",
     "title": "N-of-1 Trial of a Statin, Placebo, or No Treatment to Assess Side Effects",
     "url": "https://doi.org/10.1056/NEJMc2031173", "pmid": "33196154",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": STATIN_QUESTION,
     "appraisalVerdict": "About 90% of the symptom burden felt on the statin was also felt on placebo. It tests "
                         "the question one person at a time, which is what a person who feels tired can repeat "
                         "with their doctor. It does not show that nobody has real side effects.",
     "certainty": "moderate for the average; it cannot say which person has a real side effect",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Registered before the first patient "
                          "(NCT02668016, submitted 2016-01-19, started 2016-03)", "60 participants (registry)"],
     "appraisalOpen": ["Published as a letter: the full report was not read",
                       "People who stopped a statin within weeks may not have enrolled"],
     "appraisedAt": CHECKED, "appraisalSource": STATIN,
     "examines": [], "informs": [], "topics": ["Heart and vessels"]},
    {"id": "clear-outcomes-2023", "year": 2023,
     "design": "randomised placebo-controlled trial, 13,970 statin-intolerant people, bempedoic acid",
     "citation": "CLEAR Outcomes, Nissen et al., N Engl J Med 2023;388:1353",
     "title": "Bempedoic Acid and Cardiovascular Outcomes in Statin-Intolerant Patients",
     "url": "https://doi.org/10.1056/NEJMoa2215024", "pmid": "36876740",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": STATIN_QUESTION,
     "appraisalVerdict": "For people who cannot take a statin there is an alternative with an outcome trial: "
                         "bempedoic acid lowered LDL and major cardiovascular events against placebo, with few "
                         "muscle complaints.",
     "certainty": "high for statin-intolerant people at high risk",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Registered before the first patient "
                          "(NCT02993406, submitted 2016-12-09, started 2016-12-22)", "Double-blind"],
     "appraisalOpen": ["Funded by the maker of the drug", "Enrolled people with, or at high risk of, heart "
                       "disease: the benefit at lower risk is smaller"],
     "appraisedAt": CHECKED, "appraisalSource": STATIN,
     "examines": LDL, "informs": [], "topics": ["Heart and vessels"]},
    {"id": "q10-qu-2018", "year": 2018,
     "design": "meta-analysis of 12 small randomised trials, 575 people",
     "citation": "Qu et al., J Am Heart Assoc 2018;7:e009835",
     "title": "Effects of Coenzyme Q10 on Statin-Induced Myopathy: An Updated Meta-Analysis of Randomized "
              "Controlled Trials",
     "url": "https://doi.org/10.1161/JAHA.118.009835", "pmid": "30371340",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": STATIN_QUESTION,
     "appraisalVerdict": "Reports less muscle pain, weakness, cramps and muscle tiredness with Q10. The paper "
                         "states that it had no registered protocol, and two later meta-analyses of largely the "
                         "same trials disagree.",
     "certainty": "very low",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "No registered protocol (stated in "
                          "the full text)", "575 participants in 12 trials"],
     "appraisalOpen": ["Muscle symptoms, not general tiredness", "Fixed-effect pooling of small trials"],
     "appraisedAt": CHECKED, "appraisalSource": STATIN,
     "examines": [], "informs": [], "topics": ["Heart and vessels"]},
    {"id": "q10-kennedy-2020", "year": 2020,
     "design": "systematic review and meta-analysis of 7 randomised trials, 321 people",
     "citation": "Kennedy et al., Atherosclerosis 2020;299:1",
     "title": "Effect of Coenzyme Q10 on statin-associated myalgia and adherence to statin therapy",
     "url": "https://doi.org/10.1016/j.atherosclerosis.2020.03.006", "pmid": "32179207",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": STATIN_QUESTION,
     "appraisalVerdict": "No benefit of Q10 on muscle pain, and no more people stayed on their statin. Only two "
                         "of the trials were positive.",
     "certainty": "low",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "321 participants in 7 trials of 37 to "
                          "76 people", "No registration named in the abstract"],
     "appraisalOpen": ["Full text not read (subscription): registration not confirmed",
                       "Muscle pain, not general tiredness"],
     "appraisedAt": CHECKED, "appraisalSource": STATIN,
     "examines": [], "informs": [], "topics": ["Heart and vessels"]},
    {"id": "q10-kovacic-2025", "year": 2025,
     "design": "systematic review and meta-analysis of 7 randomised trials, 389 people, 30 to 90 days",
     "citation": "Kovacic et al., J Nutr Sci 2025;14:e72",
     "title": "Effects of coenzyme Q10 supplementation on myopathy in statin-treated patients",
     "url": "https://doi.org/10.1017/jns.2025.10043", "pmid": "41158831",
     "publicationStatus": "ok", "statusCheckedAt": CHECKED, "appraisalQuestion": STATIN_QUESTION,
     "appraisalVerdict": "Pain about one point lower on a ten-point scale, with an interval reaching almost zero "
                         "(-1.88 to -0.03); four trials positive, three not. Registered in advance, but the "
                         "trials are too small and too short to settle it.",
     "certainty": "low",
     "appraisalChecked": ["No retraction, correction or concern (PubMed)", "Registered in advance (PROSPERO "
                          "CRD42023467604, stated in the full text)", "389 participants in 7 trials of 35 to 76 "
                          "people"],
     "appraisalOpen": ["Muscle pain, not general tiredness", "Doses from 100 to 600 mg a day pooled together"],
     "appraisedAt": CHECKED, "appraisalSource": STATIN,
     "examines": [], "informs": [], "topics": ["Heart and vessels"]},
]

# Existing knowledge-layer sources a German guideline cites (its printed reference list,
# resolved to PubMed by the MVHD pipeline, PIPELINE).
GUIDELINE_CITES = [  # (guideline, study id in this graph)
    ("degam-053-024", "eas-2017-ldl"), ("degam-053-024", "pmid-36036785"),
    ("degam-053-024", "score2-diabetes-2023"), ("degam-053-048", "pmid-31504418"),
]

AFTER_CUTOFF = [  # (study, guideline, topic, summary)
    ("ctt-2026-labels", "degam-053-024", "Statin side effects",
     "Published six months after the guideline was adopted. It agrees with the guideline that muscle pain on a "
     "statin is mostly not caused by it, and adds that liver test changes are real in the first months."),
    ("whs-lpa-2026", "degam-053-024", "Lipoprotein(a)",
     "Published after the guideline: higher risk above 30 mg/dL in women, from thresholds chosen after the data. "
     "It reports relative risks, not how much Lp(a) improves a risk estimate, the question the guideline asked."),
    ("telaviv-lpa-2026", "degam-053-024", "Lipoprotein(a)",
     "Published after the guideline: a risk threshold near 50 mg/dL in one selected cohort."),
    ("lpa-horizon-2026", "degam-053-024", "Lipoprotein(a)",
     "Published after the guideline: lowering Lp(a) with pelacarsen did not reduce events. It supports the "
     "guideline's caution that an Lp(a) result has no proven treatment consequence yet."),
]

DISAGREES = [  # (guideline, guideline, topic, summary)
    ("degam-053-024", "esc-eas-2025-lipids", "LDL cholesterol",
     "DEGAM: a statin at a fixed moderate dose when the absolute 10-year risk is high enough. ESC/EAS: LDL "
     "targets by risk category, treatment intensified until the target is reached."),
    ("degam-053-024", "esc-eas-2025-lipids", "Lipoprotein(a)",
     "DEGAM: do not measure Lp(a) routinely (six societies dissent inside the guideline). ESC/EAS: measure "
     "Lp(a) at least once in every adult."),
]


# ── clinical questions: where a German answer meets another country's ──────
# German first. Another country's recommendation on a question is shown only when the question has
# a reason (question_rows): the German answer is disputed by another guideline (DISAGREES), dissented
# inside the German guideline, or met by a newer study that passed the gate (AFTER_CUTOFF). A question
# without a reason shows the German answer alone, however many other countries answer it.
QUESTIONS = [
    {"id": "q-statin-primary", "topic": "Statins in primary prevention",
     "title": "A statin to prevent a first heart attack or stroke, by absolute risk",
     "population": "adults without cardiovascular disease", "intervention": "statin",
     "matches": [], "dissent": ["DEGAM 053-024 box 9.1-2: DGK, DGIM, DDG, DHL, DGSP and DGPR dissent, a statin from a lower risk"]},
    {"id": "q-ldl-target", "topic": "LDL cholesterol",
     "title": "A fixed moderate statin dose, or treatment to an LDL target",
     "population": "adults on a statin", "intervention": "LDL target",
     "matches": ["LDL cholesterol"], "dissent": ["DEGAM 053-024 box 9.1-3: DGK, DGIM, DDG, DHL, DGSP and DGPR dissent from the fixed dose"]},
    {"id": "q-lpa-measurement", "topic": "Lipoprotein(a)",
     "title": "Measuring lipoprotein(a) once to estimate cardiovascular risk",
     "population": "adults without cardiovascular disease", "intervention": "Lp(a) measurement",
     "matches": ["Lipoprotein(a)"], "dissent": ["DEGAM 053-024 box 7-2: DGK, DGIM, DDG, DHL, DGSP and DGPR dissent, one Lp(a) measurement "
                                                "in adulthood"]},
    {"id": "q-statin-over-75", "topic": "Statins after 75",
     "title": "Starting, continuing or stopping a statin after the age of 75",
     "population": "adults older than 75", "intervention": "statin",
     "matches": [], "dissent": []},
    {"id": "q-statin-muscle", "topic": "Statin side effects",
     "title": "Muscle symptoms on a statin: what to try, and when to change",
     "population": "adults on a statin with muscle symptoms", "intervention": "statin change or stop",
     "matches": ["Statin side effects"], "dissent": ["DEGAM 053-024 box 9.1-5: DGK, DGIM, DDG, DHL, DGSP and DGPR dissent"]},
]


# Guidelines of the knowledge layer (knowledge.STUDIES) that a reason names.
SHORT_NAMES = {"esc-eas-2025-lipids": "ESC/EAS 2025 dyslipidaemia update"}


def question_rows() -> list[dict]:
    """The questions with the reasons another country's answer may be shown; none means German only."""
    names = {st["id"]: st["citation"] for st in STUDIES + LPA_STUDIES + STATIN_STUDIES}
    names.update({g["id"]: g["register"] for g in GUIDELINES} | SHORT_NAMES)
    rows = []
    for q in QUESTIONS:
        reasons = [f"disputed: {names.get(a, a)} and {names.get(b, b)} answer differently"
                   for a, b, topic, _ in DISAGREES if topic in q["matches"]]
        reasons += [f"dissent inside the guideline: {d}" for d in q["dissent"]]
        reasons += [f"newer study through the gate{' (provisional)' if c['provisional'] else ''}: "
                    f"{names.get(c['from'], c['from'])}"
                    for c in after_cutoff_rows() if c["topic"] in q["matches"]]
        rows.append({k: v for k, v in q.items() if k not in ("matches", "dissent")} | {"reasons": reasons})
    return rows


SEED_QUESTIONS = """
UNWIND $questions AS q
MERGE (c:ClinicalQuestion {id: q.id})
SET c.topic = q.topic, c.title = q.title, c.population = q.population,
    c.intervention = q.intervention, c.reasons = q.reasons
RETURN count(c) AS questions
"""


# ── the gate a newer study must pass before it is set against a guideline ──
# A guideline has already weighed the quality of the studies it cites; a newer study
# has not been through that. The gate has three layers, revised on 2026-11-21 after a
# clinical pharmacologist's review: formal criteria are too coarse,
# a study's informativeness lies in its confidence interval and not in its head count,
# and very small studies are still a reason for suspicion.
#
# 1. Form. Peer reviewed, no retraction or expression of concern, and design and plan
#    fixed before the data: a randomised trial or a meta-analysis of trials registered in
#    advance, or a prospective cohort with a registered, prespecified analysis.
#    Necessary, never enough: KETO-CTA was peer reviewed and retracted, and most weak
#    studies are neither retracted nor unregistered. registered None means not found
#    (full text not read), which fails like False.
# 2. Precision, GRADE's imprecision domain (Guyatt et al., J Clin Epidemiol 2011;64:1283),
#    for the one result that bears on the guideline:
#    - the 95% CI is rated down when it includes no effect and also an appreciable one,
#      a relative change of 25% for a yes/no outcome (0.75 or 1.25) or the minimal
#      important difference for a measured one. A CI that excludes no effect, or one
#      that includes it but rules out an appreciable change (a precise "no"), passes;
#    - the evidence must reach the optimal information size, by GRADE's rule of thumb
#      400 events for a yes/no outcome (a relative change of 25%) and 800 participants
#      for a measured one (0.2 standard deviations, alpha 0.05, power 0.8; the 2011
#      paper said 400, corrected by the U.S. GRADE Network in 2021). This replaces the
#      fixed 1,000 participants, which counted people, not information.
#    - small-study effects: a pooled result with trials of fewer than SMALL_TRIAL people
#      is held back. Such trials report effects about 48% larger than trials of 1,000
#      or more (Dechartres et al., BMJ 2013;346:f2304), so a small trial is a reason
#      for suspicion even when its interval looks narrow.
# 3. A person's reading. Risk of bias judged domain by domain with the tool for the
#    design (RoB 2, ROBINS-E, AMSTAR 2), by a person. Code checks the form and runs the
#    numbers; a model may find a passage and quote it; neither finds every concealed
#    weakness. Until a person has judged, a study that passes 1 and 2 is linked
#    provisionally and shown as such; judged at high risk, it is not linked.
# Everything that fails stays in the graph as context, with its reasons.
GATE_FACTS = {
    # id: (peer reviewed, design, registered in advance, analysis prespecified)
    "keto-cta-2025": (True, "cohort", False, False),                 # registered after the start
    "ctt-2026-labels": (True, "meta-analysis of trials", True, True),  # protocol published 2016
    "ccc-smoking-2025": (True, "pooled cohorts", False, False),       # analysis plan not public
    "lpa-horizon-2026": (True, "randomised trial", True, True),       # NCT04023552
    "epic-norfolk-lpa-2025": (True, "prospective cohort", False, False),
    "whs-lpa-2026": (True, "prospective cohort", False, False),       # hypothesis formulated after the data
    "telaviv-lpa-2026": (True, "retrospective cohort", False, False),  # threshold found in the same data
    "samson-2020": (True, "randomised trial", True, True),            # NCT02668016
    "clear-outcomes-2023": (True, "randomised trial", True, True),    # NCT02993406
    "q10-qu-2018": (True, "meta-analysis of trials", False, False),   # "no registered protocol"
    "q10-kennedy-2020": (True, "meta-analysis of trials", None, None),
    "q10-kovacic-2025": (True, "meta-analysis of trials", True, True),  # PROSPERO CRD42023467604
}
# id: the result that bears on the guideline, as read in the appraisal or the abstract.
# kind "binary": measure, estimate, CI, events in the comparison. kind "continuous":
# measure, estimate, CI, participants, the minimal important difference (MID).
# estimate None: not read, so precision cannot be judged. smallest: the smallest pooled trial.
# The MID for pain on a 10-point scale is 1 point, 10%: IMMPACT takes a fall of 10 to 20% as
# minimally important (Dworkin et al., J Pain 2008;9:105, PMID 18055266).
PRECISION = {
    "keto-cta-2025": {"kind": "continuous", "outcome": "change in plaque volume", "estimate": None,
                      "participants": 100},
    "ctt-2026-labels": {"kind": "binary", "outcome": "abnormal liver transaminases", "measure": "RR",
                        "estimate": 1.41, "ci": (1.26, 1.57), "events": 783 + 556},
    "ccc-smoking-2025": {"kind": "binary", "outcome": "cardiovascular disease, one cigarette a day or fewer",
                         "measure": "HR", "estimate": 1.47, "ci": (1.28, 1.70), "events": None},
    "lpa-horizon-2026": {"kind": "binary", "outcome": "major cardiovascular events", "measure": "HR",
                         "estimate": 1.02, "ci": (0.90, 1.15), "events": 511 + 503},
    "epic-norfolk-lpa-2025": {"kind": "binary", "outcome": "major cardiovascular events, fourth against first "
                              "fifth of Lp(a)", "measure": "HR", "estimate": 0.97, "ci": (0.87, 1.09),
                              "events": 694 + 596},
    "whs-lpa-2026": {"kind": "binary", "outcome": "major cardiovascular events above 30 mg/dL", "estimate": None,
                     "events": 3707},
    "telaviv-lpa-2026": {"kind": "binary", "outcome": "major cardiovascular events above 50 mg/dL",
                         "measure": "HR", "estimate": 1.55, "ci": (1.10, 2.17), "events": None},
    "samson-2020": {"kind": "continuous", "outcome": "symptom score", "estimate": None, "participants": 60},
    "clear-outcomes-2023": {"kind": "binary", "outcome": "major cardiovascular events", "measure": "HR",
                            "estimate": 0.87, "ci": (0.79, 0.96), "events": 819 + 927},
    "q10-qu-2018": {"kind": "continuous", "outcome": "muscle pain, points on a 10-point scale", "measure": "WMD",
                    "estimate": -1.60, "ci": (-1.75, -1.44), "participants": 575, "mid": 1.0, "smallest": None},
    "q10-kennedy-2020": {"kind": "continuous", "outcome": "muscle pain, points on a 10-point scale",
                         "measure": "WMD", "estimate": -0.42, "ci": (-1.47, 0.62), "participants": 321,
                         "mid": 1.0, "smallest": 37},
    "q10-kovacic-2025": {"kind": "continuous", "outcome": "muscle pain, points on a 10-point scale",
                         "measure": "WMD", "estimate": -0.96, "ci": (-1.88, -0.03), "participants": 389,
                         "mid": 1.0, "smallest": 35},
}
# id: (tool, judgement 'low' | 'some concerns' | 'high', who judged, date). Empty until a
# person has read the full text and its protocol; a model's rating does not count.
RISK_OF_BIAS: dict[str, tuple[str, str, str, str]] = {}

STRONG_DESIGNS = {"randomised trial", "meta-analysis of trials"}
APPRECIABLE_RATIO = (0.75, 1.25)  # GRADE: a relative change of 25%
MIN_EVENTS = 400                  # GRADE's rule of thumb for the optimal information size, yes/no outcomes
MIN_PARTICIPANTS = 800            # the same, measured outcomes (corrected 2021)
SMALL_TRIAL = 50                  # Dechartres et al. 2013: the smallest size band
BIAS_TOOL = {"randomised trial": "RoB 2", "meta-analysis of trials": "AMSTAR 2 and RoB 2 of the trials",
             "prospective cohort": "ROBINS-E"}


def _n(x: float) -> str:
    return f"{x:g}"


def precision_line(st_id: str) -> str:
    """The result the gate judged, in one line for the node panel."""
    p = PRECISION[st_id]
    if p.get("estimate") is None:
        return f"{p['outcome']}: estimate not read"
    lo, hi = p["ci"]
    size = (f"{p['events']:,} events" if p.get("events") else "events not read") if p["kind"] == "binary" \
        else f"{p['participants']:,} participants"
    return f"{p['outcome']}: {p['measure']} {_n(p['estimate'])} ({_n(lo)} to {_n(hi)}), {size}"


def precision(st_id: str) -> list[str]:
    """GRADE imprecision: why the result is not precise enough; empty when it is."""
    p = PRECISION[st_id]
    reasons = []
    if p.get("estimate") is None:
        reasons.append("effect estimate not read: precision not judged")
    else:
        lo, hi = p["ci"]
        ci = f"{p['measure']} {_n(p['estimate'])} ({_n(lo)} to {_n(hi)})"
        if p["kind"] == "binary":
            down, up = APPRECIABLE_RATIO
            if lo <= 1 <= hi and (lo < down or hi > up):
                reasons.append(f"imprecise: {ci} includes no effect and a change of 25%")
        else:
            mid = p["mid"]
            if lo <= 0 <= hi and (lo < -mid or hi > mid):
                reasons.append(f"imprecise: {ci} includes no effect and the minimal important difference "
                               f"of {_n(mid)}")
    if p["kind"] == "binary":
        if p.get("events") is None:
            reasons.append("number of events not read: information size not judged")
        elif p["events"] < MIN_EVENTS:
            reasons.append(f"information size: {p['events']:,} events, fewer than {MIN_EVENTS}")
    elif p["participants"] < MIN_PARTICIPANTS:
        reasons.append(f"information size: {p['participants']:,} participants, fewer than {MIN_PARTICIPANTS}")
    if p.get("smallest") is not None and p["smallest"] < SMALL_TRIAL:
        reasons.append(f"small-study effects: pooled trials of {p['smallest']} people, and trials under "
                       f"{SMALL_TRIAL} report larger effects")
    return reasons


def gate(st: dict) -> list[str]:
    """Why a study may not be set against a guideline; empty when it passes layers 1 and 2."""
    peer, design, registered, prespecified = GATE_FACTS[st["id"]]
    reasons = []
    if not peer:
        reasons.append("not peer reviewed (preprint)")
    if st.get("publicationStatus") != "ok":
        reasons.append(f"publication status: {st.get('publicationStatus')}")
    if design in STRONG_DESIGNS:
        if registered is None:
            reasons.append("registration not found (full text not read)")
        elif not registered:
            reasons.append("not registered before it started")
    elif design == "prospective cohort":
        if not (registered and prespecified):
            reasons.append("observational, analysis not registered and prespecified")
    else:
        reasons.append(f"design: {design}")
    reasons += precision(st["id"])
    bias = RISK_OF_BIAS.get(st["id"])
    if bias and bias[1] == "high":
        reasons.append(f"high risk of bias ({bias[0]}, judged by {bias[2]} on {bias[3]})")
    return reasons


def _with_gate(st: dict) -> dict:
    reasons = gate(st)
    design = GATE_FACTS[st["id"]][1]
    bias = RISK_OF_BIAS.get(st["id"])
    open_ = [] if bias else [f"risk of bias not yet judged by a person ({BIAS_TOOL.get(design, 'a named tool')})"]
    status = "failed" if reasons else ("provisional" if open_ else "passed")
    return st | {"gatePassed": not reasons, "gateStatus": status, "gateReasons": reasons, "gateOpen": open_,
                 "gatePrecision": precision_line(st["id"])}


def studies() -> list[dict]:
    return GUIDELINES + [_with_gate(st) for st in STUDIES + LPA_STUDIES + STATIN_STUDIES]


def about() -> list[tuple[str, str]]:
    return [(st["id"], "cardiovascular") for st in studies() if "Heart and vessels" in st.get("topics", [])] + \
        [(st["id"], "kidney") for st in studies() if "Kidney" in st.get("topics", [])] + \
        [(st["id"], "diabetes") for st in studies() if "Metabolism" in st.get("topics", [])]


def after_cutoff_rows() -> list[dict]:
    """Only studies through the gate are set against a guideline; provisionally until a person judged the bias."""
    status = {st["id"]: st["gateStatus"] for st in studies() if st.get("gateStatus")}
    return [{"from": a, "to": b, "topic": t, "summary": s, "provisional": status[a] == "provisional"}
            for a, b, t, s in AFTER_CUTOFF if status.get(a) in ("passed", "provisional")]


def disagree_rows() -> list[dict]:
    return [{"from": a, "to": b, "topic": t, "summary": s} for a, b, t, s in DISAGREES]


# Links from an earlier seed go first: a study that no longer passes the gate loses its link.
SEED_STUDY_AFTER_CUTOFF = """
OPTIONAL MATCH ()-[old:AFTER_CUTOFF_OF]->()
DELETE old
WITH count(*) AS removed
UNWIND $afterCutoff AS c
MATCH (a:Study {id: c.from})
MATCH (g:Study {id: c.to})
MERGE (a)-[k:AFTER_CUTOFF_OF {topic: c.topic}]->(g)
SET k.summary = c.summary, k.provisional = c.provisional
RETURN count(k) AS afterCutoff
"""

SEED_STUDY_DISAGREES = """
UNWIND $disagrees AS d
MATCH (a:Study {id: d.from})
MATCH (b:Study {id: d.to})
MERGE (a)-[k:DISAGREES_WITH {topic: d.topic}]->(b)
SET k.summary = d.summary
RETURN count(k) AS disagreements
"""
