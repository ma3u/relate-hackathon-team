"""German display texts for the anamnesis (anamnesis.py) and its protocols (protocols.py).

Only the words a person reads change: every linkId, option code, LOINC and SNOMED CT
code, point and band threshold stays as anamnesis.py and protocols.py define it, and
answers are stored as before (linkId, codes, the English labels). Klarbefund for Mac
shows these texts when the Mac's language is German, and the German doctor's letter
quotes them, looked up by linkId and option code. scripts/gen_swift_cypher.py copies
them into AnamnesisData.swift and ProtocolData.swift (key "de"); tests/test_german.py
checks that every question and every answer of every protocol has its German text.

Where the German comes from:

- AUDIT-C: the German AUDIT questionnaire (Suchtforschungsverbund Baden-Württemberg,
  UKL Freiburg; the form the Bundesärztekammer publishes, AlkAuditFragebogen.pdf).
  Two differences, kept on purpose because the scoring follows the WHO original that
  protocols.py scores: that form asks "mehr als 6" drinks in item 3 and prints "7 oder 8"
  in item 2, the WHO AUDIT asks "6 or more" and "7 to 9".
- PHQ-2: the two depression items of the German PHQ-D (Gesundheitsfragebogen für
  Patienten, Löwe, Spitzer, Zipfel, Herzog 2002; Gräfe et al., Diagnostica 2004;50:171),
  free to use, with its answer scale.
- FINDRISC: the wording of the Deutsche Diabetes-Stiftung's FINDRISK test where it asks
  the same thing (the form the Landesärztekammer Hessen publishes). FINDRISK changed
  two items: its age bands add 35 to 44 (1 point) and its diet item counts dark bread;
  the bands and the vegetable item here stay those of the original (Lindström &
  Tuomilehto 2003), so those labels are translated, not quoted.
- MEDAS-14: a German version was validated by Hebestreit et al., BMC Cancer 2017;17:341;
  its item wording is not freely reproduced, and protocols.py paraphrases the English
  items as yes/no questions, so these are a faithful translation of that paraphrase.
- Life's Essential 8: no German version published by the AHA; translated here from
  Lloyd-Jones et al., Circulation 2022;146:e18.
- Tobacco, family history, lipid-lowering medication, eating pattern, plant-based diet
  and the questions of the data-driven anamnesis: written for Klarbefund, translated here.
"""
from __future__ import annotations

# A dated question without a date (anamnesis.py says "that day").
DATE_FALLBACK = "an dem Tag"

YES_NO = {"yes": "Ja", "no": "Nein"}
YES_NO_UNSURE = {"yes": "Ja", "no": "Nein", "unknown": "Weiß nicht"}
LIPID_MEDICATION = {
    "text": "Nehmen Sie Medikamente zur Senkung des Cholesterins, oder haben Sie welche genommen?",
    "options": {"none": "Nie", "statin": "Ein Statin",
                "combination": "Statin plus Ezetimib oder ein anderes Medikament",
                "stopped": "Ich habe eines genommen und wieder abgesetzt"},
}
SUPPLEMENTS = {
    "text": "Nehmen Sie Vitamin D oder Calcium ein?",
    "options": {"none": "Nein", "vitamin-d": "Vitamin D", "vitamin-d-calcium": "Vitamin D und Calcium"},
}
FREQUENCY = {"never": "Nie", "<1/month": "Seltener als einmal im Monat", "1-3/month": "1- bis 3-mal im Monat",
             "1+/week": "Einmal pro Woche oder öfter"}

# ── the data-driven anamnesis (anamnesis.py) ─────────────────────────────────

ANAMNESIS = {
    "title": "Anamnese aus meinen eigenen Daten",
    "dateFallback": DATE_FALLBACK,
    "groups": {
        "ldl": "LDL-Cholesterin", "apob": "ApoB", "non-hdl": "Non-HDL-Cholesterin",
        "total-chol": "Gesamtcholesterin", "lpa": "Lp(a)", "tg": "Triglyceride", "ntprobnp": "NT-proBNP",
        "hba1c": "HbA1c", "glucose": "Nüchternglukose", "alt": "ALT (GPT)", "ast": "AST (GOT)", "ggt": "GGT",
        "creatinine": "Kreatinin", "egfr": "eGFR (Labor)", "uacr": "Albumin/Kreatinin im Urin",
        "cystatin": "Cystatin C", "cac": "Koronarkalk-Score", "crp": "hs-CRP", "ferritin": "Ferritin",
        "tsh": "TSH", "vitd": "Vitamin D",
    },
    "items": {
        "family-cvd": {
            "text": "Hatte ein Elternteil oder Geschwister früh einen Herzinfarkt, einen Schlaganfall, einen Bypass "
                    "oder einen Stent (Männer vor 55, Frauen vor 65)?",
            "options": YES_NO_UNSURE},
        "family-lipids": {
            "text": "Sind in Ihrer Familie hohes Cholesterin oder ein hohes Lp(a) bekannt (familiäre "
                    "Hypercholesterinämie)?",
            "options": YES_NO_UNSURE},
        "relatives-lpa": {
            "text": "Wurde bei jemandem in Ihrer engen Familie (Eltern, Geschwister, Kinder) Lp(a) gemessen?",
            "options": {"high": "Ja, es war erhöht", "normal": "Ja, es war normal", "no": "Nein",
                        "unknown": "Weiß nicht"}},
        "smoking": {
            "text": "Rauchen Sie, oder haben Sie früher geraucht?",
            "options": {"never": "Nie", "former": "Früher geraucht", "current": "Ich rauche"}},
        "blood-pressure": {
            "text": "Hat Ihnen eine Ärztin oder ein Arzt schon einmal gesagt, dass Ihr Blutdruck zu hoch ist?",
            "options": {"no": "Nein", "treated": "Ja, und ich nehme Medikamente", "untreated": "Ja, nicht behandelt",
                        "unknown": "Nie gemessen / weiß nicht"}},
        "home-bp": {
            "text": "Messen Sie Ihren Blutdruck zu Hause, und welche Werte sehen Sie meistens?",
            "options": {"no": "Ich messe ihn nicht", "normal": "Ja, meist unter 135/85",
                        "higher": "Ja, oft 135/85 oder höher"}},
        "family-hypertension": {
            "text": "Hat ein Elternteil oder ein Geschwister einen hohen Blutdruck?",
            "options": YES_NO_UNSURE},
        "lipid-medication": LIPID_MEDICATION,
        "diet-fat": {
            "text": "Wie oft essen Sie fettes Fleisch, Wurst, Butter, Käse oder Gebäck?",
            "options": {"daily": "Jeden Tag", "weekly": "Ein paar Mal pro Woche", "rarely": "Selten"}},
        "sample-fasting": {
            "text": "Wurde die Blutprobe ({date}) nüchtern abgenommen (8 Stunden oder länger nur Wasser)?",
            "options": {"yes": "Ja, nüchtern", "no": "Nein, ich hatte gegessen", "unknown": "Weiß nicht"}},
        "exercise-before-sample": {
            "text": "Haben Sie in den 48 Stunden vor der Blutprobe ({date}) harten Ausdauersport oder HIIT gemacht?",
            "options": YES_NO_UNSURE},
        "cardiac-symptoms": {
            "text": "Bemerken Sie etwas davon?",
            "options": {"none": "Nichts davon", "chest-pain": "Druck oder Schmerz in der Brust bei Belastung",
                        "breathless": "Atemnot beim Treppensteigen oder im Liegen",
                        "ankle-swelling": "Abends geschwollene Knöchel",
                        "palpitations": "Herzrasen oder unregelmäßiger Herzschlag"}},
        "alcohol": {
            "text": "Wie viele alkoholische Getränke trinken Sie in einer typischen Woche (ein Getränk = ein kleines "
                    "Bier oder ein Glas Wein)?",
            "options": {"none": "Keine", "1-7": "1 bis 7", "8-14": "8 bis 14", "15+": "15 oder mehr"}},
        "sugary-drinks": {
            "text": "Wie oft essen Sie Süßigkeiten oder trinken gesüßte Getränke oder Saft?",
            "options": {"daily": "Jeden Tag", "weekly": "Ein paar Mal pro Woche", "rarely": "Selten"}},
        "liver-imaging": {
            "text": "Wurde Ihre Leber schon einmal per Ultraschall oder Elastographie (FibroScan) untersucht?",
            "options": {"never": "Nie", "normal": "Ja, sie war unauffällig",
                        "fatty": "Ja, es zeigte sich eine Fettleber",
                        "elastography": "Ja, mit Elastographie (Steifigkeit gemessen)"}},
        "supplements-meds": {
            "text": "Welche Medikamente und Nahrungsergänzungsmittel nehmen Sie regelmäßig (auch pflanzliche)?",
            "options": {"none": "Keine", "some": "Einige (bitte nennen Sie sie)"}},
        "family-diabetes": {
            "text": "Hat ein Elternteil oder ein Geschwister Typ-2-Diabetes?",
            "options": YES_NO_UNSURE},
        "weight-change": {
            "text": "Wie hat sich Ihr Gewicht in den letzten zwei Jahren verändert?",
            "options": {"stable": "Stabil", "gained": "Mehr als 5 kg zugenommen",
                        "lost-planned": "Absichtlich abgenommen", "lost-unplanned": "Ungewollt abgenommen"}},
        "exercise": {
            "text": "Wie viel Bewegung, bei der Sie schneller atmen, haben Sie in einer typischen Woche?",
            "options": {"<1h": "Weniger als 1 Stunde", "1-2.5h": "1 bis 2,5 Stunden", "2.5-5h": "2,5 bis 5 Stunden",
                        "5h+": "Mehr als 5 Stunden"}},
        "painkillers": {
            "text": "Wie oft nehmen Sie Schmerzmittel wie Ibuprofen, Diclofenac oder Naproxen?",
            "options": {"rarely": "Selten oder nie", "monthly": "Ein paar Mal im Monat", "weekly": "Jede Woche",
                        "daily": "Fast jeden Tag"}},
        "creatine-protein": {
            "text": "Nehmen Sie Kreatin, oder essen Sie sehr eiweißreich (Shakes, mehr als etwa 1,6 g pro kg "
                    "Körpergewicht am Tag)?",
            "options": {"creatine": "Kreatin", "protein": "Viel Eiweiß", "both": "Beides",
                        "neither": "Keines von beiden"}},
        "fracture": {
            "text": "Haben Sie sich nach dem 40. Lebensjahr bei einem leichten Sturz einen Knochen gebrochen, oder "
                    "sind Sie kleiner geworden?",
            "options": {"no": "Nein", "fracture": "Ja, ein Knochenbruch", "height": "Ja, ich bin kleiner geworden"}},
        "supplements": SUPPLEMENTS,
        "sleep-apnoea": {
            "text": "Schnarchen Sie laut, oder hat jemand bei Ihnen Atemaussetzer im Schlaf bemerkt?",
            "options": {"no": "Nein", "snoring": "Lautes Schnarchen", "pauses": "Atemaussetzer wurden bemerkt",
                        "diagnosed": "Schlafapnoe festgestellt"}},
        "sleep-apnoea-treatment": {
            "text": "Falls bei Ihnen eine Schlafapnoe festgestellt wurde: Wird sie derzeit behandelt?",
            "options": {"none": "Keine Behandlung", "cpap": "CPAP", "splint": "Unterkieferschiene",
                        "stopped": "Behandlung beendet"}},
    },
    "rules": {
        "lipids": {
            "title": "LDL-Cholesterin oder ApoB über dem Leitlinienwert",
            "why": "LDL-Cholesterin verursacht Atherosklerose, und ApoB zählt seine Partikel; wie weit sie gesenkt "
                   "werden sollten, hängt vom Gesamtrisiko ab (ESC/EAS 2019 und das fokussierte Update 2025).",
            "ifMissing": {
                "apob": "ApoB, das bessere Einzelmaß bei hohen Triglyceriden (ESC/EAS 2019)",
                "lpa": "Lp(a), einmal im Leben bei jedem Erwachsenen (ESC/EAS 2025)",
                "cac": "Ein Koronarkalk-Score (CT ohne Kontrastmittel), falls die Entscheidung über eine "
                       "lipidsenkende Behandlung noch offen ist: Er kann das Risiko nach oben oder unten "
                       "verschieben (ESC 2021 Prävention, Klasse IIb)"}},
        "lpa": {
            "title": "Lp(a) erhöht oder über dem Grenzwert des Labors",
            "why": "Lp(a) ist überwiegend erblich und ändert sich im Leben kaum; ein erhöhtes Lp(a) kommt zum Risiko "
                   "durch LDL hinzu, und enge Verwandte sollten getestet werden (ESC/EAS 2025; EAS-Konsens 2022).",
            "tests": ["Lp(a) bei Eltern, Geschwistern und Kindern: Es ist erblich, eine Messung je Person genügt "
                      "(EAS-Konsens 2022)"]},
        "triglycerides": {
            "title": "Triglyceride über dem Leitlinienwert",
            "why": "Triglyceride steigen nach einer Mahlzeit, mit Alkohol und Zucker und bei Insulinresistenz."},
        "ntprobnp": {
            "title": "NT-proBNP am oder über dem Grenzwert",
            "why": "NT-proBNP steigt, wenn das Herz belastet ist, aber auch für ein bis zwei Tage nach hartem "
                   "Ausdauersport und wenn die Nieren weniger filtern; unter 125 ng/L ist eine Herzinsuffizienz "
                   "unwahrscheinlich (ESC 2021).",
            "tests": ["Eine Echokardiographie, wenn Beschwerden bestehen (ESC-Leitlinie Herzinsuffizienz 2021)"]},
        "glucose": {
            "title": "Blutzucker am oder über dem Grenzwert",
            "why": "HbA1c ab 5,7 % oder Nüchternglukose ab 100 mg/dL gelten als Prädiabetes (ADA 2025)."},
        "liver_enzymes": {
            "title": "Leberwerte über dem Leitlinienwert",
            "why": "Erhöhte Leberwerte weisen darauf hin, dass Fett, Alkohol, Medikamente oder "
                   "Nahrungsergänzungsmittel die Leber belasten."},
        "fib4": {
            "title": "FIB-4 zwischen den Grenzwerten oder darüber",
            "why": "Ab einem FIB-4 von 1,30 lässt sich eine Leberfibrose nicht ausschließen; EASL 2024 rät dann zu "
                   "einem zweiten Test, einer Elastographie oder dem ELF-Bluttest.",
            "tests": ["Leber-Elastographie (FibroScan) oder der ELF-Bluttest (EASL-EASD-EASO 2024)"]},
        "kidney": {
            "title": "Kreatinin über dem Leitlinienwert oder eGFR unter 60",
            "why": "Kreatinin steigt auch mit Muskelmasse, Kreatin, eiweißreicher Ernährung und hartem Sport vor "
                   "der Blutprobe; eine chronische Nierenerkrankung braucht einen Befund, der drei Monate anhält "
                   "(KDIGO 2024).",
            "ifMissing": {
                "uacr": "Albumin-Kreatinin-Quotient im Urin: KDIGO teilt Nierenerkrankungen nach eGFR und Albumin ein",
                "cystatin": "Cystatin C, für eine eGFR aus Kreatinin und Cystatin C zusammen: Kreatin, Muskeln und "
                            "eiweißreiche Ernährung erhöhen Kreatinin, aber nicht Cystatin C (KDIGO 2024)"}},
        "vitamin_d": {
            "title": "Vitamin D unter dem Bereich",
            "why": "Die Schwelle von 30 ng/mL ist der Bereich der Endocrine Society von 2011; ihre Leitlinie von "
                   "2024 setzt keinen Zielwert."},
        "exercise_bp": {
            "title": "Hoher Blutdruck unter maximaler Belastung",
            "why": "Ein systolischer Spitzendruck ab 210 mmHg (Männer) oder 190 mmHg (Frauen) im Belastungstest ist "
                   "eine überschießende Reaktion; in Studien geht er mit späterem Bluthochdruck in Ruhe einher."},
        "oxygen": {
            "title": "Wochen mit einer Sauerstoffsättigung unter 95 %",
            "why": "Niedrige nächtliche Sauerstoffwerte auf der Uhr können ein Zeichen einer Schlafapnoe sein, die "
                   "den Blutdruck und das Herzrisiko erhöht."},
        "smoking_unknown": {
            "title": "SCORE2 braucht Ihren Raucherstatus",
            "why": "SCORE2, das 10-Jahres-Risiko für Herzinfarkt und Schlaganfall, zählt jedes aktuelle Rauchen; "
                   "der Graph kann das nicht wissen."},
    },
}

# ── the protocols (protocols.py) ─────────────────────────────────────────────

SCORE_BELOW_CUT = "unter dem Grenzwert"
SCORE_AT_CUT = "am oder über dem Grenzwert"

PROTOCOLS = {
    "category": {
        "name": "Anamnese-Protokolle",
        "description": "Validierte Fragebögen und strukturierte Anamnese, codiert mit LOINC und SNOMED CT, "
                       "vorausgefüllt aus den eigenen Daten der Person."},
    "protocols": {
        "le8": {
            "name": "Life's Essential 8",
            "title": "American Heart Association: Life's Essential 8",
            "why": "Das neueste Konzept der Herzgesundheit (2022), Nachfolger von Life's Simple 7: Es nimmt den "
                   "Schlaf hinzu, nutzt Non-HDL-Cholesterin und HbA1c und bewertet jede Kennzahl von 0 bis 100, "
                   "sodass sich eine Veränderung zeigt, bevor eine Krankheit es tut.",
            "critical": [
                "Die Ernährung wird mit dem MEPA-Screener der AHA bewertet, der hier fehlt; dieser Score mittelt die "
                "sieben anderen Kennzahlen. MEDAS-14 misst stattdessen das mediterrane Muster.",
                "Die Trainingsminuten der Apple Watch zählen zügige Aktivität, nicht alltägliches Gehen, und LE8 "
                "zählt intensive Minuten doppelt: Die Uhr unterschätzt den Aktivitätswert eher, als dass sie ihn "
                "überschätzt."],
            "bands": [["niedrig", "niedrige Herz-Kreislauf-Gesundheit"],
                      ["mittel", "mittlere Herz-Kreislauf-Gesundheit"],
                      ["hoch", "hohe Herz-Kreislauf-Gesundheit"]],
            "items": {
                "le8-activity": {
                    "text": "Minuten pro Woche mit mäßiger oder intensiver Bewegung (intensive Minuten zählen doppelt)",
                    "options": {"150+": "150 oder mehr", "120-149": "120 bis 149", "90-119": "90 bis 119",
                                "60-89": "60 bis 89", "30-59": "30 bis 59", "1-29": "1 bis 29", "0": "Keine"}},
                "le8-nicotine": {
                    "text": "Tabak und Nikotin",
                    "options": {"never": "Nie geraucht", "quit-5y": "Vor 5 oder mehr Jahren aufgehört",
                                "quit-1y": "Vor 1 bis 5 Jahren aufgehört",
                                "quit-recent": "Vor weniger als einem Jahr aufgehört",
                                "vape": "Jetzt E-Zigarette oder Vape, keine Zigaretten",
                                "current": "Ich rauche, auch gelegentlich"}},
                "le8-home-smoke": {
                    "text": "Raucht jemand in Ihrer Wohnung in Innenräumen?",
                    "options": YES_NO},
                "le8-sleep": {
                    "text": "Stunden Schlaf in einer durchschnittlichen Nacht",
                    "options": {"7-9": "7 bis unter 9", "9-10": "9 bis unter 10", "6-7": "6 bis unter 7",
                                "5-6": "5 bis unter 6, oder 10 oder mehr", "4-5": "4 bis unter 5",
                                "<4": "Unter 4"}},
                "le8-bmi": {
                    "text": "Body-Mass-Index (kg/m²)",
                    "options": {"<25": "Unter 25", "25-30": "25 bis 29,9", "30-35": "30 bis 34,9",
                                "35-40": "35 bis 39,9", "40+": "40 oder mehr"}},
                "le8-lipids": {
                    "text": "Non-HDL-Cholesterin",
                    "options": {"<130": "Unter 130 mg/dL (3,4 mmol/L)", "130-159": "130 bis 159 mg/dL",
                                "160-189": "160 bis 189 mg/dL", "190-219": "190 bis 219 mg/dL",
                                "220+": "220 mg/dL (5,7 mmol/L) oder mehr"}},
                "le8-lipid-drug": {
                    "text": "Nehmen Sie derzeit ein cholesterinsenkendes Medikament?",
                    "options": YES_NO},
                "le8-glucose": {
                    "text": "Blutzucker: HbA1c (oder Nüchternglukose)",
                    "options": {"normal": "Kein Diabetes, HbA1c unter 5,7 % (Glukose unter 100 mg/dL)",
                                "prediabetes": "Kein Diabetes, HbA1c 5,7 bis 6,4 % (Glukose 100 bis 125)",
                                "dm<7": "Diabetes, HbA1c unter 7,0 %", "dm7": "Diabetes, HbA1c 7,0 bis 7,9 %",
                                "dm8": "Diabetes, HbA1c 8,0 bis 8,9 %", "dm9": "Diabetes, HbA1c 9,0 bis 9,9 %",
                                "dm10": "Diabetes, HbA1c 10 % oder mehr"}},
                "le8-bp": {
                    "text": "Blutdruck",
                    "options": {"<120": "Unter 120/80", "120-129": "120 bis 129 und unter 80",
                                "130-139": "130 bis 139 oder 80 bis 89", "140-159": "140 bis 159 oder 90 bis 99",
                                "160+": "160 oder 100 oder höher"}},
                "le8-bp-drug": {
                    "text": "Nehmen Sie ein Medikament gegen Bluthochdruck?",
                    "options": YES_NO},
            }},
        "findrisc": {
            "name": "FINDRISC",
            "title": "Finnischer Diabetes-Risiko-Score (in Deutschland: FINDRISK)",
            "why": "Der in Europa meistgenutzte Fragebogen zum Diabetesrisiko (acht Fragen, kein Bluttest); die "
                   "Deutsche Diabetes-Stiftung nutzt ihn als FINDRISK.",
            "critical": [
                "„Erhöhter Blutzucker“ heißt hier HbA1c ab 5,7 % oder Nüchternglukose ab 100 mg/dL (ADA 2025); die "
                "WHO setzt die gestörte Nüchternglukose ab 110 mg/dL an, sodass derselbe Wert in einem System "
                "zählt und im anderen nicht."],
            "bands": [["niedrig", "etwa 1 von 100 erkrankt innerhalb von 10 Jahren an Typ-2-Diabetes"],
                      ["leicht erhöht", "etwa 1 von 25 innerhalb von 10 Jahren"],
                      ["mäßig", "etwa 1 von 6 innerhalb von 10 Jahren"],
                      ["hoch", "etwa 1 von 3 innerhalb von 10 Jahren"],
                      ["sehr hoch", "etwa 1 von 2 innerhalb von 10 Jahren"]],
            "items": {
                "findrisc-age": {
                    "text": "Wie alt sind Sie?",
                    "options": {"<45": "Unter 45 Jahre", "45-54": "45 bis 54 Jahre", "55-64": "55 bis 64 Jahre",
                                "65+": "Älter als 64 Jahre"}},
                "findrisc-bmi": {
                    "text": "Wie ist bei Ihnen das Verhältnis von Körpergröße zu Körpergewicht (Body-Mass-Index, kg/m²)?",
                    "options": {"<25": "Unter 25", "25-30": "25 bis 30", ">30": "Über 30"}},
                "findrisc-waist": {
                    "text": "Welchen Taillenumfang messen Sie unterhalb der Rippen (meist auf Höhe des Bauchnabels)?",
                    "options": {"small": "Männer unter 94 cm, Frauen unter 80 cm",
                                "medium": "Männer 94 bis 102 cm, Frauen 80 bis 88 cm",
                                "large": "Männer über 102 cm, Frauen über 88 cm"}},
                "findrisc-activity": {
                    "text": "Haben Sie täglich mindestens 30 Minuten körperliche Bewegung, bei der Arbeit oder in der "
                            "Freizeit (Bewegung im Alltag zählt mit)?",
                    "options": YES_NO},
                "findrisc-vegetables": {
                    "text": "Wie oft essen Sie Gemüse, Obst oder Beeren?",
                    "options": {"daily": "Jeden Tag", "not-daily": "Nicht jeden Tag"}},
                "findrisc-bp-drugs": {
                    "text": "Wurden Ihnen schon einmal Medikamente gegen Bluthochdruck verordnet?",
                    "options": YES_NO},
                "findrisc-glucose": {
                    "text": "Wurden bei Ihnen schon einmal zu hohe Blutzuckerwerte festgestellt (bei einer "
                            "Untersuchung, während einer Krankheit, in der Schwangerschaft)?",
                    "options": YES_NO},
                "findrisc-family": {
                    "text": "Wurde bei mindestens einem Mitglied Ihrer Verwandtschaft Diabetes (Typ 1 oder Typ 2) "
                            "diagnostiziert?",
                    "options": {"no": "Nein",
                                "distant": "Ja, in der entfernten Verwandtschaft (Großeltern, Tante, Onkel, "
                                           "Cousine oder Cousin)",
                                "close": "Ja, in der nahen Verwandtschaft (Eltern, Geschwister oder eigene Kinder)"}},
            }},
        "audit-c": {
            "name": "AUDIT-C",
            "title": "AUDIT der WHO, die drei Fragen zum Alkoholkonsum",
            "why": "Die drei Konsumfragen des AUDIT der WHO: das Screening, das die meisten Hausarztpraxen und die "
                   "EU-Empfehlungen nutzen.",
            "critical": [
                "Eine sichere Mindestmenge ist nicht belegt: Wer gelegentlich oder wenig trank, lebte nicht länger "
                "als lebenslang Abstinente, sobald die Verzerrungen der Studien kontrolliert wurden (Zhao 2023). Die "
                "ESC-Präventionsleitlinie 2021 rät zu höchstens 100 g Alkohol pro Woche."],
            "bands": [[SCORE_BELOW_CUT, "kein Hinweis auf riskanten Alkoholkonsum"],
                      [SCORE_AT_CUT, "riskanter Alkoholkonsum ist wahrscheinlich: Sprechen Sie mit Ihrer Ärztin "
                                     "oder Ihrem Arzt darüber"]],
            "items": {
                "audit-c-1": {
                    "text": "Wie oft trinken Sie Alkohol?",
                    "options": {"never": "Nie", "monthly": "Einmal im Monat oder seltener",
                                "2-4-month": "2- bis 4-mal pro Monat", "2-3-week": "2- bis 3-mal pro Woche",
                                "4-week": "4-mal oder öfter pro Woche"}},
                "audit-c-2": {
                    "text": "Wenn Sie an einem Tag Alkohol trinken, wie viele alkoholhaltige Getränke trinken Sie dann "
                            "typischerweise (ein Getränk = z. B. 0,33 l Bier oder ein kleines Glas Wein)?",
                    "options": {"1-2": "1 oder 2", "3-4": "3 oder 4", "5-6": "5 oder 6", "7-9": "7 bis 9",
                                "10+": "10 oder mehr"}},
                "audit-c-3": {
                    "text": "Wie oft trinken Sie 6 oder mehr alkoholische Getränke bei einer Gelegenheit?",
                    "options": {"never": "Nie", "less-monthly": "Seltener als einmal im Monat",
                                "monthly": "Einmal im Monat", "weekly": "Einmal pro Woche",
                                "daily": "Täglich oder fast täglich"}},
            }},
        "tobacco": {
            "name": "Tabakkonsum",
            "title": "Tabakkonsum, wie ihn die International Patient Summary erfasst",
            "why": "Der Raucherstatus ist die eine Angabe für SCORE2, die der Graph nicht kennen kann; codiert wie in "
                   "der Patientenkurzakte reist er mit der Akte der Person durch Europa.",
            "critical": [
                "SCORE2 kennt nur Raucher oder Nichtraucher und zählt jedes aktuelle Rauchen. Schon eine Zigarette am "
                "Tag bringt etwa die Hälfte des Herz- und Schlaganfallrisikos von 20 am Tag (Hackshaw 2018); keine "
                "Studie zeigt eine sichere geringere Menge."],
            "items": {
                "smoking": {
                    "text": "Rauchen Sie, oder haben Sie früher geraucht?",
                    "options": {"never": "Nie", "former": "Früher geraucht", "current": "Ich rauche, auch gelegentlich"}},
                "tobacco-amount": {
                    "text": "Wie viel rauchen Sie?",
                    "options": {"occasional": "Weniger als eine Zigarette am Tag", "1-9": "1 bis 9 am Tag",
                                "10-19": "10 bis 19 am Tag", "20-39": "20 bis 39 am Tag", "40+": "40 oder mehr am Tag"}},
                "tobacco-quit": {
                    "text": "Wann haben Sie aufgehört?",
                    "options": {"<1y": "Vor weniger als einem Jahr", "1-5y": "Vor 1 bis 5 Jahren",
                                "5y+": "Vor 5 oder mehr Jahren"}},
                "tobacco-vape": {
                    "text": "Nutzen Sie E-Zigaretten oder Vapes?",
                    "options": YES_NO},
                "tobacco-home": {
                    "text": "Raucht jemand in Ihrer Wohnung in Innenräumen?",
                    "options": YES_NO},
            }},
        "medas": {
            "name": "MEDAS-14",
            "title": "Fragebogen zur Mittelmeerkost (MEDAS, PREDIMED)",
            "why": "Die 14 Fragen aus PREDIMED, der Studie, in der eine Mittelmeerkost Herzinfarkte und Schlaganfälle "
                   "senkte (Estruch 2018); kurz und an einem vollständigen Ernährungsfragebogen validiert.",
            "critical": [
                "Einen Punkt gibt es für 7 oder mehr Gläser Wein pro Woche. Das war der Stand von 2011; neuere Daten "
                "finden keinen Nutzen des Trinkens (Zhao 2023). Der Score bleibt wie veröffentlicht, aber fangen Sie "
                "seinetwegen nicht mit dem Trinken an.",
                "Der Score misst die Ähnlichkeit mit dem mediterranen Muster. Eine ketogene oder kohlenhydratarme "
                "Ernährung schneidet bei Obst und Hülsenfrüchten schlecht ab, was immer sie sonst bewirkt."],
            "bands": [["geringe Einhaltung", "weit vom mediterranen Muster entfernt"],
                      ["mittlere Einhaltung", "teilweise mediterran"],
                      ["hohe Einhaltung", "nah am Muster, das PREDIMED getestet hat"]],
            "items": {
                "medas-1": {"text": "Ist Olivenöl Ihr hauptsächliches Fett zum Kochen?", "options": YES_NO},
                "medas-2": {"text": "Verwenden Sie 4 oder mehr Esslöffel Olivenöl am Tag (zum Kochen, für Salate, beim "
                                    "Essen außer Haus)?", "options": YES_NO},
                "medas-3": {"text": "Essen Sie 2 oder mehr Portionen Gemüse am Tag (mindestens eine roh oder als Salat)?",
                            "options": YES_NO},
                "medas-4": {"text": "Essen Sie 3 oder mehr Stück Obst am Tag?", "options": YES_NO},
                "medas-5": {"text": "Essen Sie weniger als eine Portion rotes Fleisch, Hamburger oder Wurst am Tag?",
                            "options": YES_NO},
                "medas-6": {"text": "Essen Sie weniger als eine Portion Butter, Margarine oder Sahne am Tag?",
                            "options": YES_NO},
                "medas-7": {"text": "Trinken Sie weniger als ein gesüßtes oder kohlensäurehaltiges Getränk am Tag?",
                            "options": YES_NO},
                "medas-8": {"text": "Trinken Sie 7 oder mehr Gläser Wein pro Woche? (siehe Hinweis: kein Grund, damit "
                                    "anzufangen)", "options": YES_NO},
                "medas-9": {"text": "Essen Sie 3 oder mehr Portionen Hülsenfrüchte (Linsen, Bohnen, Kichererbsen) pro "
                                    "Woche?", "options": YES_NO},
                "medas-10": {"text": "Essen Sie 3 oder mehr Portionen Fisch oder Meeresfrüchte pro Woche?",
                             "options": YES_NO},
                "medas-11": {"text": "Essen Sie gekaufte Süßigkeiten oder gekauftes Gebäck seltener als 3-mal pro Woche?",
                             "options": YES_NO},
                "medas-12": {"text": "Essen Sie 3 oder mehr Portionen Nüsse pro Woche?", "options": YES_NO},
                "medas-13": {"text": "Essen Sie lieber Huhn, Pute oder Kaninchen als Rind, Schwein, Hamburger oder Wurst?",
                             "options": YES_NO},
                "medas-14": {"text": "Essen Sie 2-mal pro Woche oder öfter Gerichte mit einer in Olivenöl geschmorten "
                                     "Soße aus Tomaten, Zwiebeln oder Knoblauch?", "options": YES_NO},
            }},
        "family-cvd": {
            "name": "Herz-Kreislauf-Erkrankungen in der Familie",
            "title": "Familienanamnese (FHIR FamilyMemberHistory), gelesen nach der Regel der ESC 2021",
            "why": "Welcher Verwandte und in welchem Alter entscheidet, ob eine Familienanamnese zählt: Die ESC 2021 "
                   "nutzt sie nur dann als Risikomodifikator, wenn die Herzkrankheit früh begann.",
            "critical": [
                "Eine Herzkrankheit, die mit 70 oder später beginnt, ist häufig und zählt in der ESC 2021 nicht als "
                "familiäre Belastung. Familien teilen Gewohnheiten ebenso wie Gene: Eltern, die rauchten, sich wenig "
                "bewegten oder ungünstig aßen, geben weniger Risiko weiter als dieselbe Krankheit mit 50."],
            "items": {
                "family-cvd-who": {
                    "text": "Wer hatte einen Herzinfarkt, einen Schlaganfall, einen Bypass oder einen Stent?",
                    "options": {"none": "Niemand", "father": "Vater", "mother": "Mutter", "brother": "Ein Bruder",
                                "sister": "Eine Schwester", "unknown": "Weiß nicht"}},
                "family-cvd-father-age": {
                    "text": "Wie alt war Ihr Vater beim ersten Mal?",
                    "options": {"<55": "Unter 55", "55-64": "55 bis 64", "65+": "65 oder älter",
                                "unknown": "Weiß nicht"}},
                "family-cvd-mother-age": {
                    "text": "Wie alt war Ihre Mutter beim ersten Mal?",
                    "options": {"<65": "Unter 65", "65+": "65 oder älter", "unknown": "Weiß nicht"}},
                "family-cvd-sibling-age": {
                    "text": "War es früh: ein Bruder vor 55 oder eine Schwester vor 65?",
                    "options": YES_NO_UNSURE},
                "family-lipids": {
                    "text": "Ist in Ihrer Familie eine familiäre Hypercholesterinämie, sehr hohes Cholesterin oder ein "
                            "hohes Lp(a) bekannt?",
                    "options": YES_NO_UNSURE},
            }},
        "lipid-therapy": {
            "name": "Lipidsenkende Medikamente",
            "title": "Cholesterinsenkende Medikamente und seit wann (FHIR MedicationStatement)",
            "why": "Lipidwerte unter einem Statin zeigen das Medikament, nicht die Person: Mit den Daten kann der "
                   "Graph behandelte von unbehandelten Werten unterscheiden.",
            "critical": [
                "Ein Statin senkt das LDL-Cholesterin innerhalb von Wochen um 30 bis 50 %. Der niedrigste Wert einer "
                "Reihe ist oft der behandelte; die Risikoscores gehen vom unbehandelten Wert aus, wenn man ihnen "
                "nichts anderes sagt."],
            "items": {
                "lipid-medication": LIPID_MEDICATION,
                "lipid-from": {"text": "Seit wann (Jahr und Monat)?", "options": {}},
                "lipid-until": {"text": "Bis wann (Jahr und Monat)?", "options": {}},
            }},
        "diet-pattern": {
            "name": "Ernährungsweise und Fasten",
            "title": "Ernährungsweise und Fasten, codiert mit SNOMED CT",
            "why": "Die Ernährung verändert, wie Lipid-, Blutzucker- und Leberwerte zu lesen sind: Eine ketogene "
                   "Ernährung senkt die Triglyceride und erhöht HDL, und bei manchen Menschen erhöht sie "
                   "LDL-Cholesterin und ApoB stark.",
            "critical": [
                "Unter kohlenhydratarmer oder ketogener Ernährung LDL und ApoB mit Blick auf die Ernährung lesen; "
                "Triglyceride und der TG/HDL-Quotient sehen dann besser aus als bei gemischter Kost."],
            "items": {
                "diet-pattern": {
                    "text": "Wie ernähren Sie sich überwiegend?",
                    "options": {"mixed": "Gemischt", "mediterranean": "Mediterran", "low-carb": "Kohlenhydratarm",
                                "keto": "Ketogen", "vegetarian": "Vegetarisch", "vegan": "Vegan"}},
                "fasting-habit": {
                    "text": "Fasten Sie regelmäßig?",
                    "options": {"no": "Nein", "time-restricted": "Zeitlich begrenztes Essen (z. B. 16:8)",
                                "long": "Fastenzeiten von einem Tag oder länger"}},
            }},
        "plant-based": {
            "name": "Pflanzenbasierte Ernährung",
            "title": "Vegetarisch oder vegan: die Ernährungsgruppe nach AHS-2 und die Nährstoffe, die die DGE 2024 "
                     "als kritisch nennt",
            "why": "Die Folgefragen zu einer vegetarischen oder veganen Antwort. Vier Fragen zu Fleisch, Fisch, Eiern "
                   "und Milchprodukten ergeben die Ernährungsgruppe nach der Adventist Health Study 2; die übrigen "
                   "fragen, wie die Nährstoffe gedeckt sind, die bei pflanzlicher Ernährung fehlen können (DGE "
                   "2024), und Ihre Laborwerte dazu stehen neben den Fragen.",
            "critical": [
                "Vitamin B12 im Serum kann im Laborbereich bleiben, während die Speicher sinken: Holotranscobalamin "
                "oder Methylmalonsäure zeigen einen frühen Mangel (Herrmann 2003). Ein hoher Folatwert, häufig bei "
                "pflanzlicher Ernährung, hält Hämoglobin und MCV normal, während B12 sinkt; die Nerven schützt er "
                "nicht.",
                "Der Körper speichert B12 für Jahre, daher sagt ein normaler Wert in den ersten Jahren veganer "
                "Ernährung wenig über später.",
                "TSH zeigt die Schilddrüsenfunktion, nicht die Jodzufuhr; Jod im Urin zeigt sie. Jod ist in "
                "Deutschland unabhängig von der Ernährung knapp, bei veganer Ernährung noch knapper (DGE 2024).",
                "Veganer hatten in EPIC-Oxford mehr Hüftfrakturen als Fleischesser (Tong 2020); Calcium, Vitamin D "
                "und Eiweiß erklärten einen Teil davon."],
            "items": {
                "plant-meat": {
                    "text": "Wie oft essen Sie Fleisch oder Geflügel (auch Wurst, Schinken und Fleischbrühe)?",
                    "options": FREQUENCY},
                "plant-fish": {"text": "Wie oft essen Sie Fisch oder Meeresfrüchte?", "options": FREQUENCY},
                "plant-eggs": {"text": "Wie oft essen Sie Eier (auch in Gebackenem)?", "options": FREQUENCY},
                "plant-dairy": {"text": "Wie oft essen Sie Milch, Joghurt oder Käse?", "options": FREQUENCY},
                "plant-since": {
                    "text": "Wie lange essen Sie schon ohne Fleisch?",
                    "options": {"<1y": "Weniger als ein Jahr", "1-3y": "1 bis 3 Jahre", "3y+": "3 Jahre oder länger"}},
                "plant-b12": {
                    "text": "Nehmen Sie Vitamin B12 ein?",
                    "options": {"daily": "Eine Tablette oder Tropfen, täglich oder an den meisten Tagen",
                                "weekly": "Eine hohe Dosis ein- oder zweimal pro Woche",
                                "injection": "Spritzen von der Ärztin oder vom Arzt",
                                "fortified": "Nur angereicherte Lebensmittel oder B12-Zahnpasta", "no": "Nein"}},
                "plant-iodine": {
                    "text": "Verwenden Sie zu Hause Jodsalz, oder nehmen Sie Jod ein?",
                    "options": {"salt": "Jodsalz", "supplement": "Eine Jodtablette (oder beides)", "no": "Nein",
                                "unknown": "Weiß nicht"}},
                "plant-omega3": {"text": "Nehmen Sie ein Algenöl mit DHA und EPA?", "options": YES_NO},
                "plant-calcium": {
                    "text": "Haben Sie jeden Tag eine Calciumquelle: Pflanzendrinks oder Joghurtalternativen mit "
                            "zugesetztem Calcium, mit Calcium hergestellten Tofu oder ein calciumreiches Mineralwasser?",
                    "options": {"yes": "Ja, täglich", "sometimes": "An manchen Tagen", "no": "Nein"}},
                "plant-legumes": {
                    "text": "Essen Sie jeden Tag Hülsenfrüchte, Tofu, Tempeh oder Seitan?",
                    "options": {"yes": "Ja, täglich", "sometimes": "An manchen Tagen", "no": "Selten"}},
                "supplements": SUPPLEMENTS,
            }},
        "phq-2": {
            "name": "PHQ-2",
            "title": "Gesundheitsfragebogen für Patienten (PHQ-D), zwei Fragen",
            "why": "Ständige Müdigkeit ist oft eine gedrückte Stimmung und kein fehlender Laborwert; zwei Fragen "
                   "prüfen das, bevor weitere Tests angeordnet werden.",
            "critical": ["Ein Screening, keine Diagnose. Die ESC 2021 zählt Depression zu den Faktoren, die das "
                         "Herzrisiko erhöhen."],
            "bands": [[SCORE_BELOW_CUT, "kein Hinweis auf eine gedrückte Stimmung"],
                      [SCORE_AT_CUT, "eine gedrückte Stimmung ist möglich: Der vollständige PHQ-9 oder eine Ärztin "
                                     "oder ein Arzt kann es klären"]],
            "items": {
                "phq2-1": {
                    "text": "Wie oft fühlten Sie sich im Verlauf der letzten 2 Wochen beeinträchtigt durch: wenig "
                            "Interesse oder Freude an Ihren Tätigkeiten?",
                    "options": {"0": "Überhaupt nicht", "1": "An einzelnen Tagen", "2": "An mehr als der Hälfte der Tage",
                                "3": "Beinahe jeden Tag"}},
                "phq2-2": {
                    "text": "Wie oft fühlten Sie sich im Verlauf der letzten 2 Wochen beeinträchtigt durch: "
                            "Niedergeschlagenheit, Schwermut oder Hoffnungslosigkeit?",
                    "options": {"0": "Überhaupt nicht", "1": "An einzelnen Tagen", "2": "An mehr als der Hälfte der Tage",
                                "3": "Beinahe jeden Tag"}},
            }},
    },
    # The bands family_summary() and plant_summary() give (protocols.py), by their English label.
    "summaryBands": {
        "none": "keine", "premature": "früh", "age unknown": "Alter unbekannt", "later in life": "später im Leben",
        "vegan": "vegan", "lacto-ovo-vegetarian": "ovo-lacto-vegetarisch", "lacto-vegetarian": "lacto-vegetarisch",
        "ovo-vegetarian": "ovo-vegetarisch", "pesco-vegetarian": "pescetarisch",
        "semi-vegetarian": "teilvegetarisch", "non-vegetarian": "nicht vegetarisch",
        "not vegetarian": "nicht vegetarisch", "vegetarian": "vegetarisch",
    },
    "prefill": {
        "age": "Ihr Alter, aus dem angegebenen Geburtsjahr",
        "bmi": "Ihr neuester Body-Mass-Index, sonst Ihr neuestes Gewicht und Ihre Größe",
        "waist": "Ihr neuester Taillenumfang",
        "watch_minutes": "Trainingsminuten der Apple Watch, Mittel der letzten 12 Wochen",
        "watch_daily30": "Trainingsminuten der Apple Watch: ja, wenn das Mittel der letzten 12 Wochen 30 Minuten am "
                         "Tag oder mehr beträgt",
        "watch_sleep": "Schlaf laut Apple Watch, Mittel der letzten 12 Wochen",
        "nonhdl": "Ihr neuestes Non-HDL-Cholesterin, sonst Gesamt- minus HDL-Cholesterin desselben Tages",
        "glucose": "Ihr neuester HbA1c, sonst die Nüchternglukose",
        "glucose_ever_high": "alle HbA1c- und Glukosewerte: ja, wenn einer 5,7 % oder 100 mg/dL erreichte",
        "bp": "Ihre neueste Blutdruckmessung",
        "bp_drug": "Ihre Anamnese-Antwort zur Blutdruckbehandlung",
        "lipid_drug": "Ihre Antwort zu cholesterinsenkenden Medikamenten",
        "tobacco": "Ihre Antworten zum Rauchen",
        "home_smoke": "Ihre Antwort zum Rauchen in der Wohnung",
        "family_diabetes": "Ihre Anamnese-Antwort zu Diabetes bei Eltern und Geschwistern",
        "alcohol_none": "Ihre Anamnese-Antwort zu Alkohol",
        "wine_week": "Ihre Anamnese-Antwort zu Alkohol",
        "diet:meat": "Ihre Antwort zur Ernährungsweise: vegetarisch oder vegan heißt kein Fleisch",
        "diet:fish": "Ihre Antwort zur Ernährungsweise: vegetarisch oder vegan heißt kein Fisch",
        "diet:eggs": "Ihre Antwort zur Ernährungsweise: vegan heißt keine Eier",
        "diet:dairy": "Ihre Antwort zur Ernährungsweise: vegan heißt keine Milchprodukte",
    },
}


def missing() -> list[str]:
    """Every English text that has no German text here (empty when complete)."""
    from . import anamnesis, protocols
    out = []
    a = ANAMNESIS
    for g in anamnesis.GROUPS:
        if not a["groups"].get(g["id"]):
            out.append(f"group {g['id']}")
    for it in anamnesis.ITEMS:
        de = a["items"].get(it["linkId"]) or {}
        if not de.get("text"):
            out.append(f"anamnesis {it['linkId']}: text")
        if ("{date}" in it["text"]) != ("{date}" in (de.get("text") or "")):
            out.append(f"anamnesis {it['linkId']}: {{date}}")
        for code, _, _ in it["options"]:
            if not (de.get("options") or {}).get(code):
                out.append(f"anamnesis {it['linkId']}: option {code}")
    for r in anamnesis.RULES:
        de = a["rules"].get(r["id"]) or {}
        for key in ("title", "why"):
            if not de.get(key):
                out.append(f"rule {r['id']}: {key}")
        if len(de.get("tests") or []) != len(r.get("tests") or []):
            out.append(f"rule {r['id']}: tests")
        for gid in r.get("ifMissing") or {}:
            if not (de.get("ifMissing") or {}).get(gid):
                out.append(f"rule {r['id']}: ifMissing {gid}")
    for p in protocols.PROTOCOLS:
        de = PROTOCOLS["protocols"].get(p["id"]) or {}
        for key in ("name", "title", "why"):
            if not de.get(key):
                out.append(f"protocol {p['id']}: {key}")
        if len(de.get("critical") or []) != len(p.get("critical") or []):
            out.append(f"protocol {p['id']}: critical")
        if len(de.get("bands") or []) != len(p.get("bands") or []):
            out.append(f"protocol {p['id']}: bands")
        for it in p["items"]:
            di = (de.get("items") or {}).get(it["linkId"]) or {}
            if not di.get("text"):
                out.append(f"protocol {p['id']} {it['linkId']}: text")
            for x in it["options"]:
                if not (di.get("options") or {}).get(x["code"]):
                    out.append(f"protocol {p['id']} {it['linkId']}: option {x['code']}")
    for key in protocols.PREFILL:
        if not PROTOCOLS["prefill"].get(key):
            out.append(f"prefill {key}")
    return out
