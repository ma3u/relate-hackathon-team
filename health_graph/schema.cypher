// Local Sovereign Health Graph: schema (Relate / openCypher)
// Keys follow the EHDS Hub's *code* (ui/src/lib/patient/app-observations.ts,
// scripts/load_fhir_neo4j.py), not the design spec, so `relate push` merges cleanly.
// Run once per store; every statement is idempotent.

// ── L3 FHIR ──────────────────────────────────────────────────────────────────
CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (n:Patient) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT observation_resource_id IF NOT EXISTS FOR (n:Observation) REQUIRE n.resourceId IS UNIQUE;
CREATE CONSTRAINT diagnostic_report_resource_id IF NOT EXISTS FOR (n:DiagnosticReport) REQUIRE n.resourceId IS UNIQUE;
CREATE CONSTRAINT document_reference_resource_id IF NOT EXISTS FOR (n:DocumentReference) REQUIRE n.resourceId IS UNIQUE;
CREATE CONSTRAINT provenance_resource_id IF NOT EXISTS FOR (n:Provenance) REQUIRE n.resourceId IS UNIQUE;
CREATE CONSTRAINT organization_name IF NOT EXISTS FOR (n:Organization) REQUIRE n.name IS UNIQUE;
CREATE INDEX observation_source_report IF NOT EXISTS FOR (n:Observation) ON (n.sourceReport);
CREATE INDEX observation_effective_date IF NOT EXISTS FOR (n:Observation) ON (n.effectiveDate);

// ── L4 OMOP ──────────────────────────────────────────────────────────────────
CREATE CONSTRAINT omop_person_id IF NOT EXISTS FOR (n:OMOPPerson) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT omop_measurement_id IF NOT EXISTS FOR (n:OMOPMeasurement) REQUIRE n.id IS UNIQUE;

// ── L5 Ontology ──────────────────────────────────────────────────────────────
CREATE CONSTRAINT loinc_code IF NOT EXISTS FOR (n:LoincCode) REQUIRE n.code IS UNIQUE;
CREATE CONSTRAINT ncbi_taxon_code IF NOT EXISTS FOR (n:NcbiTaxon) REQUIRE n.code IS UNIQUE;

// ── Search ───────────────────────────────────────────────────────────────────
// Find values by the words on the paper report (German labels) or the LOINC name.
CREATE FULLTEXT INDEX observation_text IF NOT EXISTS FOR (n:Observation) ON EACH [n.display, n.sourceLine];
CREATE FULLTEXT INDEX loinc_text IF NOT EXISTS FOR (n:LoincCode) ON EACH [n.display];

// ── Knowledge layer (health_graph/knowledge.py) ─────────────────────────────
// Health risks, the scores that estimate them, the measures they use, and the
// guideline and optimal ranges from Klarbefund's reference-ranges.ts.
CREATE CONSTRAINT health_risk_id IF NOT EXISTS FOR (n:HealthRisk) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT risk_score_id IF NOT EXISTS FOR (n:RiskScore) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT reference_range_id IF NOT EXISTS FOR (n:ReferenceRange) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT score_result_id IF NOT EXISTS FOR (n:ScoreResult) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT knowledge_id IF NOT EXISTS FOR (n:Knowledge) REQUIRE n.id IS UNIQUE;
