"""Named read-only queries for the demo (CLI, tests, and later the app and MCP)."""

QUERIES: dict[str, tuple[str, str]] = {
    "reports": (
        "All imported reports with lab, source and how many values the Hub would accept",
        """
        MATCH (p:Patient)-[:HAS_DIAGNOSTIC_REPORT]->(dr:DiagnosticReport)-[:HAS_RESULT]->(o:Observation)
        OPTIONAL MATCH (dr)-[:DERIVED_FROM]->(doc:DocumentReference)
        RETURN dr.effectiveDate AS date, dr.performer AS lab, doc.title AS document,
               collect(DISTINCT o.sourceKind)[0] AS source, count(o) AS values,
               sum(CASE WHEN o.hubEligible THEN 1 ELSE 0 END) AS hubReady,
               sum(CASE WHEN o.duplicateOf IS NOT NULL THEN 1 ELSE 0 END) AS alsoInAnotherReport
        ORDER BY date
        """,
    ),
    "trend": (
        "Trend of one analyte (param loinc) across all reports, with provenance; each measurement once",
        """
        MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(lc:LoincCode {code: $loinc})
        WHERE o.duplicateOf IS NULL
        OPTIONAL MATCH (dr:DiagnosticReport)-[:HAS_RESULT]->(o)
        OPTIONAL MATCH (copy:Observation)-[:SAME_AS]->(o)
        RETURN left(o.effectiveDate, 10) AS date, o.display AS label,
               coalesce(o.comparator, '') + toString(o.valueQuantity) AS value, o.unit AS unit,
               o.referenceText AS printedRange, o.sourceKind AS source,
               o.verifiedByPatientAt IS NOT NULL AS verified,
               coalesce(dr.performer, o.performer) AS lab, count(copy) AS alsoInOtherReports
        ORDER BY date
        """,
    ),
    "wearables": (
        "Apple Health weekly means (resting HR, HRV, steps, weight) sent by Klarbefund",
        """
        MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation {sourceReport: 'apple-health-weekly'})
        RETURN o.display AS metric, o.effectiveStart AS weekStart, o.valueQuantity AS mean,
               o.unit AS unit, o.performer AS devices
        ORDER BY metric, weekStart
        """,
    ),
    "analytes": (
        "Every coded analyte with how often and when it was measured (copies counted once)",
        """
        MATCH (o:Observation)-[:CODED_BY]->(lc:LoincCode)
        WHERE o.duplicateOf IS NULL
        RETURN lc.code AS loinc, lc.display AS name, count(o) AS n,
               min(o.effectiveDate) AS first, max(o.effectiveDate) AS last
        ORDER BY n DESC, loinc
        """,
    ),
    "unmapped": (
        "Values without a LOINC code, and the reason (honesty about data quality)",
        """
        MATCH (o:Observation) WHERE o.code IS NULL
        OPTIONAL MATCH (o)-[:IDENTIFIES]->(t:NcbiTaxon)
        RETURN o.display AS label, o.effectiveDate AS date, t.code AS ncbiTaxon,
               o.unmappedReason AS reason
        ORDER BY date
        """,
    ),
    "duplicates": (
        "Values that appear in more than one report: the copy kept, and where else it was found",
        """
        MATCH (copy:Observation)-[:SAME_AS]->(kept:Observation)
        OPTIONAL MATCH (kr:DiagnosticReport)-[:HAS_RESULT]->(kept)
        OPTIONAL MATCH (cr:DiagnosticReport)-[:HAS_RESULT]->(copy)
        RETURN left(kept.effectiveDate, 10) AS date, kept.display AS label,
               coalesce(kr.title, kr.performer) AS keptIn, kept.sourceKind AS keptSource,
               coalesce(cr.title, cr.performer) AS copyIn, copy.sourceKind AS copySource
        ORDER BY date, label
        """,
    ),
    "scores": (
        "Risk scores stored for the person, with the values each one used (python -m health_graph scores)",
        """
        MATCH (:Patient)-[:HAS_SCORE]->(sr:ScoreResult)-[:OF]->(rs:RiskScore)-[:ESTIMATES]->(h:HealthRisk)
        OPTIONAL MATCH (sr)-[:FROM]->(o:Observation)
        RETURN rs.name AS score, h.name AS risk, sr.value AS value, sr.unit AS unit, sr.band AS band,
               sr.light AS light, sr.demographics AS demographics, left(sr.computedAt, 10) AS computed,
               collect(o.display + ' ' + toString(o.valueQuantity) + ' ' + coalesce(o.unit, '')
                       + ' (' + left(o.effectiveDate, 10) + ')') AS inputs, rs.source AS source
        ORDER BY score
        """,
    ),
    "ranges": (
        "Guideline range and optimal band for one LOINC code (param loinc), with the source",
        """
        MATCH (rr:ReferenceRange)-[:APPLIES_TO]->(:LoincCode {code: $loinc})
        RETURN rr.analyteKey AS analyte, rr.ucum AS unit, rr.sex AS sex,
               rr.guidelineLow AS guidelineLow, rr.guidelineHigh AS guidelineHigh,
               rr.optimalLow AS optimalLow, rr.optimalHigh AS optimalHigh,
               rr.summary AS summary, rr.sourceLabel AS source
        ORDER BY unit, sex
        """,
    ),
    "risk": (
        "One health risk (param risk: cardiovascular, diabetes, kidney, liver, fitness): its scores and markers",
        """
        MATCH (h:HealthRisk {id: $risk})
        OPTIONAL MATCH (rs:RiskScore)-[:ESTIMATES]->(h)
        OPTIONAL MATCH (m:LoincCode)-[k:MARKER_OF]->(h)
        OPTIONAL MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(m)
        WHERE o.duplicateOf IS NULL
        WITH h, rs, m, k, o ORDER BY o.effectiveDate DESC
        WITH h, rs, m, k, collect(o)[0] AS last
        RETURN h.name AS risk, collect(DISTINCT rs.name) AS scores, m.code AS loinc, m.display AS measure,
               last.valueQuantity AS latest, last.unit AS unit, left(last.effectiveDate, 10) AS date,
               k.source AS source
        ORDER BY date DESC
        """,
    ),
    "provenance": (
        "Where one value (param resourceId) came from: line on the paper, OCR, document, agent",
        """
        MATCH (o:Observation {resourceId: $resourceId})<-[:HAS_RESULT]-(dr:DiagnosticReport)
        OPTIONAL MATCH (dr)-[:DERIVED_FROM]->(doc:DocumentReference)
        OPTIONAL MATCH (pv:Provenance)-[:TARGET]->(dr)
        RETURN o.display AS label, o.valueQuantity AS value, o.unit AS unit,
               o.sourceKind AS source, o.sourceLine AS line, o.ocrConfidence AS ocr,
               o.originalReading AS correctedFrom, o.verifiedByPatientAt AS verifiedAt,
               doc.title AS document, pv.activity AS activity, pv.agent AS agent
        """,
    ),
    "search": (
        "Full-text search (param q) over printed labels, source lines and LOINC names",
        """
        CALL () {
          MATCH (o:Observation)
          SEARCH o IN (FULLTEXT INDEX observation_text FOR $q LIMIT 20) SCORE AS score
          RETURN o, score
          UNION
          MATCH (lc:LoincCode)
          SEARCH lc IN (FULLTEXT INDEX loinc_text FOR $q LIMIT 20) SCORE AS score
          MATCH (o:Observation)-[:CODED_BY]->(lc)
          RETURN o, score
        }
        RETURN o.display AS label, o.code AS loinc, o.effectiveDate AS date,
               o.valueQuantity AS value, o.unit AS unit, max(score) AS score
        ORDER BY score DESC, date
        """,
    ),
    "omop": (
        "OMOP CDM measurements (concept id 0, LOINC as source value)",
        """
        MATCH (op:OMOPPerson)-[:HAS_MEASUREMENT]->(om:OMOPMeasurement)
        RETURN om.measurementDate AS date, om.measurementSourceValue AS loinc,
               om.valueAsNumber AS value, om.unitSourceValue AS unit,
               om.measurementConceptId AS conceptId
        ORDER BY date, loinc
        """,
    ),
    "stats": (
        "Node counts per label",
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label",
    ),
}
