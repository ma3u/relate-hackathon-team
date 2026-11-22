"""The doctor's letter: what Klarbefund for Mac reads to prepare a visit to the GP or a specialist.

The letter itself is built in Swift (swift/Sources/HealthGraph/DoctorLetter.swift):
the latest lab tests exactly as printed, every marker's trend compared only with a
reference range in the same unit that applied on the value's date, the Apple Watch
weekly means (recent 12 weeks against the year before), sport and activity, the
latest anamnesis answer per question and the questions for the doctor. These are
the reads it runs; scripts/gen_swift_cypher.py copies them into Cypher.swift, so the
Python and the Swift graphs answer them alike (tests/test_letter.py runs them here).

A value seen in two reports counts once: every read filters `o.duplicateOf IS NULL`.
"""

PATIENT = """
MATCH (p:Patient)
RETURN p.birthYear AS birthYear, p.gender AS sex
LIMIT 1
"""

# Every lab value (not the Apple Watch weekly means), with the report it was printed on.
LAB_VALUES = """
MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)
WHERE o.duplicateOf IS NULL AND coalesce(o.sourceKind, '') <> 'device-weekly-mean'
OPTIONAL MATCH (r:DiagnosticReport)-[:HAS_RESULT]->(o)
RETURN o.resourceId AS id, o.code AS code, o.display AS display, o.valueQuantity AS value,
       o.comparator AS comparator, o.unit AS unit, o.effectiveDate AS date,
       o.referenceLow AS labLow, o.referenceHigh AS labHigh, o.referenceText AS labText,
       o.sourceLine AS sourceLine, o.sourceKind AS sourceKind,
       r.resourceId AS report, r.title AS title, r.performer AS performer, r.effectiveDate AS reportDate
ORDER BY date, display
"""

# The Apple Watch weekly means (resting heart rate, HRV, blood oxygen, exercise minutes, steps, VO2 max ...).
DEVICE_VALUES = """
MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)
WHERE o.sourceKind = 'device-weekly-mean' AND o.valueQuantity IS NOT NULL
RETURN o.code AS code, o.display AS display, o.valueQuantity AS value, o.unit AS unit, o.effectiveDate AS date
ORDER BY code, date
"""

# The guideline ranges of the given codes; the letter picks the one in the value's unit valid on its date.
RANGES = """
MATCH (r:ReferenceRange)-[:APPLIES_TO]->(c:LoincCode)
WHERE c.code IN $codes
RETURN c.code AS code, r.ucum AS ucum, r.sex AS sex, r.guidelineLow AS low, r.guidelineHigh AS high,
       r.validFrom AS validFrom, r.validUntil AS validUntil, r.sourceLabel AS source,
       r.supersededBy AS supersededBy
ORDER BY code, validFrom
"""

# The health risks the knowledge layer tracks, with their marker codes (MARKER_OF).
RISKS = """
MATCH (h:HealthRisk)
OPTIONAL MATCH (c:LoincCode)-[:MARKER_OF]->(h)
RETURN h.id AS id, h.name AS name, collect(DISTINCT c.code) AS codes
ORDER BY id
"""

# How one risk raises another (RAISES_RISK_OF), in both directions from the risk in focus.
RISK_LINKS = """
MATCH (a:HealthRisk)-[k:RAISES_RISK_OF]->(b:HealthRisk)
WHERE a.id = $risk OR b.id = $risk
RETURN a.id AS fromId, a.name AS fromName, b.id AS toId, b.name AS toName, k.summary AS summary
ORDER BY fromId, toId
"""

# The latest answer per question, the data-driven anamnesis and the protocols alike.
ANSWERS = """
MATCH (:Patient)-[:HAS_RESPONSE]->(r:QuestionnaireResponse)-[:HAS_ANSWER]->(a:Answer)
WITH a.linkId AS linkId, a, r ORDER BY a.authored DESC
WITH linkId, collect([a, r])[0] AS newest
WITH linkId, newest[0] AS a, newest[1] AS r
RETURN linkId, a.question AS question, a.labels AS labels, a.text AS text, a.context AS context,
       a.authored AS authored, a.riskFactor AS riskFactor, r.protocol AS protocol
ORDER BY authored DESC, linkId
"""
