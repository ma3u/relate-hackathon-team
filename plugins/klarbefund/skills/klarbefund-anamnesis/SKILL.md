---
name: klarbefund-anamnesis
description: Personal anamnesis from the user's own health graph in Klarbefund for Mac. Use when the user asks where their health risks are, what to improve first, why they feel tired, or to take or update their medical history; when they want validated questionnaires (Life's Essential 8, FINDRISC, AUDIT-C, MEDAS-14, PHQ-2, tobacco, family history, statin dates, diet) filled in from their lab values and Apple Watch data; or to store what a reading concluded. Needs the Klarbefund Health Graph extension (tools get_schema, read_cypher, anamnesis_protocols, save_protocol_answers, save_assessment).
---

# Personal anamnesis from the health graph

The user's lab reports and Apple Watch data sit in a Neo4j Relate graph on their Mac, kept by Klarbefund for Mac. You read it through the **Klarbefund Health Graph** extension (read-only) and hand confirmed answers and findings back to the app, which stores them. This skill is the method; it holds no data. Every number comes from the graph in this conversation.

If the extension's tools are missing, say so and stop: the user opens Klarbefund for Mac and clicks **Connect Claude Desktop**. Do not guess values.

## 1. Read the risk profile

1. Call `get_schema`, then `anamnesis_protocols` (the questionnaires, what the user stored before, earlier assessments) and, if present, `anamnesis_plan` (findings in the data, questions left).
2. Find the main risk: the health risk with the most recent values outside their range (`read_cypher`; count a value seen in two reports once: `o.duplicateOf IS NULL`). Show it as a short table: value, unit, date, lab, the range and its source. Newest first.
3. Rank the protocols by that profile. Cardiovascular: tobacco, lipid-lowering medication (with months), family history, Life's Essential 8, eating pattern. Glucose: FINDRISC. Liver: AUDIT-C. Tiredness: PHQ-2. Vegetarian or vegan answer: the plant-based follow-up.

## 2. Ask, protocol by protocol

- Prefill what the graph answers (each question's `prefill` says from what). Show the value, its date and the option it falls in, for the user to confirm. Prefer the newest value **not** measured under a medicine the user names.
- Ask only the rest: at most four questions at a time, the options as given, skipping questions whose `enableWhen` does not hold. Never ask what the data shows or what was answered in the last year.
- Store each confirmed protocol with `save_protocol_answers`, prefilled answers with `prefilled` (where from) and `observation` (the value's resourceId).
- Give the score, its band and the protocol's critical note in one sentence (wine in MEDAS-14, any smoking in SCORE2, late family history).

## 3. Check the data while you go

These become findings:

| Kind | Look for |
|---|---|
| `treated` | values measured in the months of a statin, or under a diet the user names (ketogenic diets can raise LDL and ApoB a lot) |
| `data-quality` | values of one day that do not fit together (for example LDL against total cholesterol, HDL and triglycerides), the same values in two reports, an implausible unit: say which paper to check |
| `discrepancy` | a watch value the answer contradicts (sleep, activity) |
| `risk`, `habit` | what moves the main risk most (smoking, lipids, sleep) |
| `ask-doctor`, `test` | questions for the appointment; tests that close a gap (ApoB, Lp(a) once in life, holotranscobalamin, urine albumin) |

## 4. Close the reading and store it

1. One table: protocol, score and band, what it means for the user. Then the findings, each one line with its values and dates.
2. When the user confirms, call `save_assessment`: `title` (for example "Anamnesis 2026-11-15"), `summary` (two to five sentences), `protocols` (the ids read), `findings` with `kind`, `severity` (`info`, `watch`, `high`), `title`, `text`, `observations` (Observation resourceIds from `read_cypher`) and `risks` (`cardiovascular`, `diabetes`, `kidney`, `liver`, `bone`, `fitness`).

## Rules

- Not a diagnosis and not medical advice: say what the data shows and what to ask. Chest pain, shortness of breath, fainting or signs of a stroke belong with a doctor or emergency service now.
- Every number with its date and source, so the user can check it on the paper.
- Store nothing the user has not seen and confirmed.
- Answer in the language the user writes in.
