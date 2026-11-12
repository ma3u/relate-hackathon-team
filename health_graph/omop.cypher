// Local FHIR -> OMOP CDM v5.4 transform, ported from the EHDS Hub's
// neo4j/fhir-to-omop-transform.cypher (plain MERGE/SET, no APOC).
// Difference: reads the app's property names (valueQuantity, effectiveDate),
// which the Hub transform currently misses (it reads value / dateTime).
// Concept ids stay 0: Athena is not on the device; LOINC goes into measurementSourceValue.

// 1. OMOPPerson: year of birth only, never names (Hub #475)
MATCH (p:Patient)
MERGE (op:OMOPPerson {id: 'omop-person-' + p.id})
SET op.personSourceValue = p.id,
    op.yearOfBirth = p.birthYear,
    op.genderConceptId = CASE p.gender WHEN 'male' THEN 8507 WHEN 'female' THEN 8532 ELSE 0 END
MERGE (p)-[:MAPPED_TO]->(op)
RETURN count(op) AS omop_persons;

// 2. OMOPMeasurement from numeric laboratory / vital-sign Observations
MATCH (p:Patient)-[:HAS_OBSERVATION]->(o:Observation)
WHERE o.category IN ['laboratory', 'vital-signs'] AND o.valueQuantity IS NOT NULL AND o.code IS NOT NULL
  AND o.duplicateOf IS NULL
MATCH (p)-[:MAPPED_TO]->(op:OMOPPerson)
MERGE (om:OMOPMeasurement {id: 'omop-meas-' + o.resourceId})
SET om.measurementDate = left(o.effectiveDate, 10),
    om.measurementSourceValue = o.code,
    om.measurementConceptId = 0,
    om.valueAsNumber = o.valueQuantity,
    om.operatorSourceValue = o.comparator,
    om.unitSourceValue = o.unit,
    om.rangeLow = o.referenceLow,
    om.rangeHigh = o.referenceHigh,
    om.measurementTypeSourceValue = o.sourceKind
MERGE (o)-[:MAPPED_TO]->(om)
MERGE (op)-[:HAS_MEASUREMENT]->(om)
RETURN count(om) AS omop_measurements;

// 2b. A copy of a value another report already carries (Observation.duplicateOf,
// see store.py) is not a second measurement
MATCH (o:Observation)-[:MAPPED_TO]->(om:OMOPMeasurement)
WHERE o.duplicateOf IS NOT NULL
DETACH DELETE om
RETURN count(*) AS omop_duplicates_removed;

// 3. Vocabulary bridge OMOPMeasurement -> LoincCode
MATCH (o:Observation)-[:CODED_BY]->(lc:LoincCode)
MATCH (o)-[:MAPPED_TO]->(om:OMOPMeasurement)
MERGE (om)-[:CODED_BY]->(lc)
RETURN count(*) AS omop_coded;
