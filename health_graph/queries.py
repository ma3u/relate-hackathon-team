"""Named read-only queries for the demo (CLI, tests, and later the app and MCP)."""

QUERIES: dict[str, tuple[str, str]] = {
    "reports": (
        "All imported reports with lab, source and how many values the Hub would accept",
        """
        MATCH (p:Patient)-[:HAS_DIAGNOSTIC_REPORT]->(dr:DiagnosticReport)-[:HAS_RESULT]->(o:Observation)
        OPTIONAL MATCH (dr)-[:DERIVED_FROM]->(doc:DocumentReference)
        RETURN dr.effectiveDate AS date, dr.performer AS lab, doc.title AS document,
               collect(DISTINCT o.sourceKind)[0] AS source, count(o) AS values,
               sum(CASE WHEN o.hubEligible THEN 1 ELSE 0 END) AS hubReady
        ORDER BY date
        """,
    ),
    "trend": (
        "Trend of one analyte (param loinc) across all reports, with provenance",
        """
        MATCH (:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[:CODED_BY]->(lc:LoincCode {code: $loinc})
        OPTIONAL MATCH (dr:DiagnosticReport)-[:HAS_RESULT]->(o)
        RETURN left(o.effectiveDate, 10) AS date, o.display AS label,
               coalesce(o.comparator, '') + toString(o.valueQuantity) AS value, o.unit AS unit,
               o.referenceText AS printedRange, o.sourceKind AS source,
               o.verifiedByPatientAt IS NOT NULL AS verified,
               coalesce(dr.performer, o.performer) AS lab
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
        "Every coded analyte with how often and when it was measured",
        """
        MATCH (o:Observation)-[:CODED_BY]->(lc:LoincCode)
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
