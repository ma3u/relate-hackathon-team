import Foundation
import Relate
import Testing

@testable import HealthGraph

/// Port of tests/test_health_graph.py: same synthetic fixtures, same expectations,
/// so the Swift and Python graphs are interchangeable.
enum Fixtures {
  static let root = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent()
  static let fhirDir = root.appendingPathComponent("fixtures/fhir")
  static var bundles: [URL] {
    (try? FileManager.default.contentsOfDirectory(at: fhirDir, includingPropertiesForKeys: nil))?
      .filter { $0.pathExtension == "json" }.sorted { $0.path < $1.path } ?? []
  }
  static let golden = fhirDir.appendingPathComponent("2026-09-04-praxis-muster.json")
  static let wearables = root.appendingPathComponent("fixtures/apple-health-weekly.json")

  static func bundle(_ url: URL) throws -> JSONObject {
    try FHIR.loadBundle(Data(contentsOf: url))
  }

  static func tempStore() throws -> String {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir.appendingPathComponent("health.rl").path
  }

  /// A store with the three synthetic reports and the OMOP transform.
  static func loadedStore() throws -> (HealthStore, String) {
    let path = try tempStore()
    let store = try HealthStore(path: path)
    try store.initSchema()
    for url in bundles { try store.importReport(FHIR.parseBundle(bundle(url))) }
    try store.omopTransform()
    return (store, path)
  }
}

@Suite("Parsing (no database)")
struct ParsingTests {
  @Test func goldenBundleMatchesHubContract() throws {
    let p = try FHIR.parseBundle(Fixtures.bundle(Fixtures.golden))
    #expect(p.patientId == "example-patient")
    #expect(p.reportId == "rpt-2026-09-04")
    #expect(p.observations.count == 7)
    #expect(p.observations[0]["resourceId"] == "example-patient-rpt-2026-09-04-1")
    let hba1c = try #require(p.observations.first { $0["code"] == "4548-4" })
    #expect(hba1c["valueQuantity"] == .float(5.4) && hba1c["unit"] == "%")
    #expect(hba1c["sourceKind"] == "ocr-transcribed")
    #expect(hba1c["verifiedByPatientAt"] == "2026-09-05T08:01:00Z")
  }

  @Test func unmappedValueKeepsReasonAndNoFakeCode() throws {
    let p = try FHIR.parseBundle(Fixtures.bundle(Fixtures.golden))
    let microbe = try #require(p.observations.first { $0["display"] == "Akkermansia muciniphila" })
    #expect(microbe["code"] == .null)
    #expect(microbe["unmappedReason"]?.stringValue?.contains("NCBI Taxonomy") == true)
    #expect(microbe["taxonCode"] == "239935")
    #expect(microbe["hubEligible"] == false)
  }

  @Test func hubEligibilityFollowsAppRecordRules() throws {
    let digital = try FHIR.parseBundle(Fixtures.bundle(Fixtures.bundles[0]))
    #expect(Set(digital.observations.compactMap { $0["status"]?.stringValue }) == ["final"])
    #expect(digital.hubReady == 0)
    #expect(try FHIR.parseBundle(Fixtures.bundle(Fixtures.golden)).hubReady == 6)
  }

  /// Without Bundle.identifier the id is a content hash, identical to Python's.
  @Test(arguments: [
    ("2026-03-12-labor-beispielstadt.json", "rpt-5ab49633f448"),
    ("2026-06-10-praxis-muster.json", "rpt-fc11d51dd45b"),
    ("2026-09-04-praxis-muster.json", "rpt-24dba7bd0575"),
  ])
  func fallbackReportIdMatchesPython(file: String, expected: String) throws {
    var b = try Fixtures.bundle(Fixtures.fhirDir.appendingPathComponent(file))
    b.removeValue(forKey: "identifier")
    #expect(try FHIR.parseBundle(b).reportId == expected)
  }

  @Test func headerReportIdWins() throws {
    let p = try FHIR.parseBundle(Fixtures.bundle(Fixtures.golden), reportId: "3f2a")
    #expect(p.reportId == "3f2a" && p.observations[0]["resourceId"] == "example-patient-3f2a-1")
  }

  @Test func rejectsBundleWithoutOnePatient() {
    #expect(throws: HealthGraphError.self) {
      try FHIR.parseBundle(["resourceType": "Bundle", "entry": [Any]()])
    }
  }

  /// LocalGraphExport.swift adds uncoded Observations: label, raw unit, reason.
  @Test func unmappedValueFromKlarbefundLocalExport() throws {
    var b = try Fixtures.bundle(Fixtures.golden)
    var entries = b["entry"] as! [Any]
    entries.append([
      "resource": [
        "resourceType": "Observation", "id": "unmapped-1", "status": "preliminary",
        "extension": [
          ["url": FHIR.ext + "source-kind", "valueCode": "ocr-transcribed"],
          ["url": FHIR.ext + "source-line", "valueString": "Zonulin  >48,2  ng/ml  < 55"],
        ],
        "code": [
          "text": "Zonulin",
          "extension": [
            [
              "url": FHIR.dataAbsent, "valueCode": "unknown",
              "_valueCode": [
                "extension": [
                  ["url": FHIR.rendered, "valueString": "Not coded: not in the analyte dictionary"]
                ]
              ],
            ]
          ],
        ],
        "effectiveDateTime": "2026-09-04",
        "valueQuantity": ["value": NSNumber(value: 48.2), "unit": "ng/ml", "comparator": ">"],
        "referenceRange": [["high": ["value": 55, "unit": "ng/ml"], "text": "< 55"]],
      ] as JSONObject
    ])
    b["entry"] = entries
    let p = try FHIR.parseBundle(b)
    let z = try #require(p.observations.last)
    #expect(z["code"] == .null && z["display"] == "Zonulin")
    #expect(z["unmappedReason"] == "Not coded: not in the analyte dictionary")
    #expect(z["valueQuantity"] == .float(48.2) && z["unit"] == "ng/ml" && z["comparator"] == ">")
    #expect(z["hubEligible"] == false)
    #expect(z["resourceId"]?.stringValue?.hasSuffix("-8") == true)
  }
}

@Suite("Apple Health weekly means")
struct WearableTests {
  @Test func fixtureIsAcceptedInFull() throws {
    let (rows, skipped) = FHIR.parseWearables(try Fixtures.bundle(Fixtures.wearables), patientId: "p")
    #expect(rows.count == 16 && skipped.isEmpty)
    #expect(rows.allSatisfy { $0["sourceKind"] == "device-weekly-mean" })
  }

  @Test func newMetricsAreAcceptedAndImplausibleRefused() {
    func obs(_ code: String, _ unit: String, _ value: Double, start: String = "2026-11-02",
      end: String = "2026-11-08", category: String = "vital-signs") -> Any {
      [
        "resource": [
          "resourceType": "Observation", "id": "w-\(code)", "status": "final",
          "category": [["coding": [["system": FHIR.observationCategory, "code": category]]]],
          "code": ["coding": [["system": FHIR.loinc, "code": code, "display": code]], "text": code],
          "effectivePeriod": ["start": start, "end": end],
          "valueQuantity": [
            "value": NSNumber(value: value), "unit": unit, "system": FHIR.ucum, "code": unit,
          ],
        ] as JSONObject
      ]
    }
    let bundle: JSONObject = [
      "resourceType": "Bundle",
      "entry": [
        obs("94122-9", "mL/min/kg", 42.3), obs("9279-1", "/min", 14.8), obs("59408-5", "%", 96.4),
        obs("41981-2", "kcal/d", 610, category: "activity"), obs("41982-0", "%", 18.2),
        obs("55411-3", "min/d", 31, category: "activity"),
        obs("93832-4", "h/d", 7.2, category: "activity"),
        obs("93831-6", "min/d", 64, category: "activity"),
        obs("93829-0", "min/d", 101, category: "activity"),
        obs("93830-8", "min/d", 270, category: "activity"),
        obs("59408-5", "%", 12.0, start: "2026-11-09", end: "2026-11-15"),
      ],
    ]
    let (rows, skipped) = FHIR.parseWearables(bundle, patientId: "p")
    #expect(rows.count == 10)
    #expect(skipped.map(\.reason) == ["the value is not plausible"])
  }

  @Test func refusesWrongUnitDuplicatesAndNonFinal() {
    func obs(_ id: String, status: String = "final", unit: String = "/min") -> Any {
      [
        "resource": [
          "resourceType": "Observation", "id": id, "status": status,
          "code": ["coding": [["system": FHIR.loinc, "code": "40443-4"]]],
          "effectivePeriod": ["start": "2026-11-02", "end": "2026-11-08"],
          "valueQuantity": ["value": 55, "system": FHIR.ucum, "code": unit],
        ] as JSONObject
      ]
    }
    let bundle: JSONObject = [
      "resourceType": "Bundle",
      "entry": [obs("a"), obs("b"), obs("c", status: "preliminary"), obs("d", unit: "bpm")],
    ]
    let (rows, skipped) = FHIR.parseWearables(bundle, patientId: "p")
    #expect(rows.count == 1)
    #expect(
      skipped.map(\.reason) == [
        "the same metric and week twice", "a device value is sent as final",
        "a number in /min (UCUM) is required",
      ])
  }
}

@Suite("Graph", .serialized)
struct GraphTests {
  func stats(_ store: HealthStore) throws -> [String: Int] {
    Dictionary(
      uniqueKeysWithValues: try store.run("stats").map {
        ($0["label"]?.stringValue ?? "", Int($0["n"]?.intValue ?? 0))
      })
  }

  @Test func counts() throws {
    let (store, _) = try Fixtures.loadedStore()
    let s = try stats(store)
    #expect(s["Observation"] == 21)
    #expect(s["DiagnosticReport"] == 3)
    #expect(s["LoincCode"] == 6)
    #expect(s["OMOPMeasurement"] == 18)
    #expect(s["Patient"] == 1 && s["OMOPPerson"] == 1)
  }

  @Test func reimportReplacesInsteadOfDuplicating() throws {
    let (store, _) = try Fixtures.loadedStore()
    try store.importReport(FHIR.parseBundle(Fixtures.bundle(Fixtures.golden)))
    try store.omopTransform()
    let s = try stats(store)
    #expect(s["Observation"] == 21 && s["OMOPMeasurement"] == 18)
  }

  @Test func trendIsOrderedWithProvenance() throws {
    let (store, _) = try Fixtures.loadedStore()
    let rows = try store.run("trend", ["loinc": "4548-4"])
    #expect(rows.map { $0["date"]?.plain } == ["2026-03-12", "2026-06-10", "2026-09-04"])
    #expect(rows.map { $0["value"]?.plain } == ["5.9", "5.6", "5.4"])
    #expect(rows.first?["source"] == "lab-issued-digital")
  }

  @Test func comparatorSurvives() throws {
    let (store, _) = try Fixtures.loadedStore()
    #expect(try store.run("trend", ["loinc": "2276-4"]).last?["value"] == "<10")
  }

  @Test func unmappedQuery() throws {
    let (store, _) = try Fixtures.loadedStore()
    let rows = try store.run("unmapped")
    #expect(rows.count == 3 && rows.allSatisfy { $0["ncbiTaxon"] == "239935" })
  }

  @Test func provenanceShowsOcrCorrection() throws {
    let (store, _) = try Fixtures.loadedStore()
    let rows = try store.run("provenance", ["resourceId": "example-patient-rpt-2026-09-04-7"])
    let row = try #require(rows.first)
    #expect(rows.count == 1)
    #expect(row["label"] == "Körpergewicht" && row["value"] == 80)
    #expect(row["correctedFrom"] == "Körpergewicht 30 kg")
    #expect(row["document"] == "laborbefund-2026-09-04.pdf")
  }

  @Test(arguments: [
    ("Ferritin", "Ferritin"), ("cholesterol", "LDL-Cholesterin"), ("weight", "Körpergewicht"),
    ("Körpergewicht", "Körpergewicht"),
  ])
  func fulltextSearch(term: String, label: String) throws {
    let (store, _) = try Fixtures.loadedStore()
    #expect(try store.run("search", ["q": .string(term)]).first?["label"] == .string(label))
  }

  @Test func omopUsesConceptZeroAndLoincSourceValue() throws {
    let (store, _) = try Fixtures.loadedStore()
    let rows = try store.run("omop")
    #expect(rows.count == 18)
    #expect(Set(rows.compactMap { $0["conceptId"]?.intValue }) == [0])
    #expect(
      Set(["4548-4", "2089-1"]).isSubset(of: Set(rows.compactMap { $0["loinc"]?.stringValue })))
  }

  @Test func wearablesMeetLabValuesOnOneLoincCode() throws {
    var (store, path) = try Fixtures.loadedStore()
    let (stored, skipped) = try store.receiveWearables(Fixtures.bundle(Fixtures.wearables))
    #expect(stored == 16 && skipped.isEmpty)
    // sending again replaces the weekly means
    #expect(try store.receiveWearables(Fixtures.bundle(Fixtures.wearables)).stored == 16)
    store = try HealthStore(path: Fixtures.tempStore())  // release the writer
    let reader = try HealthStore(path: path, readOnly: true)
    let weight = try reader.connection.query(
      """
      MATCH (o:Observation)-[:CODED_BY]->(:LoincCode {code: '29463-7'})
      RETURN o.sourceKind AS kind, count(*) AS n ORDER BY kind
      """
    ).records
    // weight from paper, from the lab's digital report and from Apple Health: one LoincCode
    // (same counts as the Python implementation)
    #expect(
      weight.map { $0["kind"]?.plain ?? "" } == [
        "device-weekly-mean", "lab-issued-digital", "ocr-transcribed",
      ])
    #expect(weight.map { $0["n"]?.intValue ?? 0 } == [4, 1, 2])
    #expect(try reader.count("Observation") == 21 + 16)
  }

  @Test func plainRowsForAppScreens() throws {
    let (store, _) = try Fixtures.loadedStore()
    let trend = try store.rows(query: "trend", ["loinc": "4548-4"])
    #expect(trend.map { $0["value"] } == ["5.9", "5.6", "5.4"])
    let n = try store.rows(cypher: "MATCH (o:Observation) WHERE o.code IS NULL RETURN count(o) AS n")
    #expect(n == [["n": "3"]])
  }

  @Test func readOnlyNeverCreatesAStore() throws {
    let path = try Fixtures.tempStore()
    #expect(throws: (any Error).self) { try HealthStore(path: path, readOnly: true) }
    #expect(!FileManager.default.fileExists(atPath: path))
  }
}

@Suite("Same Cypher as the Python reference")
struct CypherParityTests {
  func python(_ file: String) throws -> String {
    try String(contentsOf: Fixtures.root.appendingPathComponent("health_graph/\(file)"), encoding: .utf8)
  }

  @Test func schemaAndOmopMatch() throws {
    #expect(HealthStore.statements(Cypher.schema) == HealthStore.statements(try python("schema.cypher")))
    #expect(HealthStore.statements(Cypher.omop) == HealthStore.statements(try python("omop.cypher")))
  }

  /// Every Swift statement and named query appears verbatim (modulo indentation) in the Python source.
  @Test func storeAndQueriesMatch() throws {
    func squash(_ s: String) -> String {
      s.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
    let store = squash(try python("store.py"))
    for statement in [
      Cypher.deleteReport, Cypher.upsertReport, Cypher.upsertObservations, Cypher.unlinkSameMeasurements,
      Cypher.linkSameMeasurements, Cypher.replaceWearables, Cypher.upsertWearables,
    ] {
      #expect(store.contains(squash(statement)))
    }
    let queries = squash(try python("queries.py"))
    for (name, query) in Queries.all {
      #expect(queries.contains(squash(query.cypher)), "query \(name) drifted")
    }
  }
}

/// Port of the duplicate tests in tests/test_health_graph.py (Nov 12, 2026:
/// one sheet scanned twice, a value repeated on one report).
@Suite("Duplicates", .serialized)
struct DuplicateTests {
  static func observations(_ bundle: JSONObject) -> [JSONObject] {
    ((bundle["entry"] as? [JSONObject]) ?? []).compactMap { $0["resource"] as? JSONObject }
      .filter { $0["resourceType"] as? String == "Observation" }
  }

  /// The golden bundle as if the laboratory had sent its own digital file.
  static func asDigital(_ bundle: JSONObject) -> JSONObject {
    var bundle = bundle
    bundle["entry"] = ((bundle["entry"] as? [JSONObject]) ?? []).map { entry in
      var entry = entry
      guard var resource = entry["resource"] as? JSONObject,
        resource["resourceType"] as? String == "Observation"
      else { return entry }
      resource["extension"] = ((resource["extension"] as? [JSONObject]) ?? []).map { x in
        var x = x
        if (x["url"] as? String)?.hasSuffix("source-kind") == true { x["valueCode"] = "lab-issued-digital" }
        return x
      }
      entry["resource"] = resource
      return entry
    }
    return bundle
  }

  @Test func aValuePrintedTwiceOnOneReportIsOneValue() throws {
    var bundle = try Fixtures.bundle(Fixtures.golden)
    var again = Self.observations(bundle)[5]  // Akkermansia: overview table and detail section
    let firstId = again["id"] as? String
    again["id"] = "obs-6-again"
    bundle["entry"] = ((bundle["entry"] as? [JSONObject]) ?? []) + [["resource": again]]
    let parsed = try FHIR.parseBundle(bundle)
    #expect(parsed.observations.count == 7)
    let folded = parsed.observations.first { $0["fhirId"]?.stringValue == firstId }
    #expect(folded?["repeatedOnReport"]?.intValue == 2)
  }

  @Test func theSameReportTwiceCountsEachMeasurementOnce() throws {
    let (store, _) = try Fixtures.loadedStore()
    try store.importReport(FHIR.parseBundle(Self.asDigital(Fixtures.bundle(Fixtures.golden)), reportId: "rescan"))
    try store.omopTransform()
    let stats = Dictionary(
      uniqueKeysWithValues: try store.run("stats").map {
        ($0["label"]?.stringValue ?? "", Int($0["n"]?.intValue ?? 0))
      })
    #expect(stats["Observation"] == 28)  // nothing deleted
    #expect(stats["OMOPMeasurement"] == 18)  // but measured once
    let dups = try store.run("duplicates")
    #expect(dups.count == 7)
    #expect(Set(dups.compactMap { $0["keptSource"]?.stringValue }) == ["lab-issued-digital"])
    let trend = try store.run("trend", ["loinc": "4548-4"])
    #expect(trend.map { $0["date"]?.plain } == ["2026-03-12", "2026-06-10", "2026-09-04"])
    #expect(trend.last?["alsoInOtherReports"]?.intValue == 1)
    let hba1c = try store.run("analytes").first { $0["loinc"]?.stringValue == "4548-4" }
    #expect(hba1c?["n"]?.intValue == 3)
  }

  @Test func removingTheCopyRestoresTheFirst() throws {
    let (store, _) = try Fixtures.loadedStore()
    try store.importReport(FHIR.parseBundle(Self.asDigital(Fixtures.bundle(Fixtures.golden)), reportId: "rescan"))
    _ = try store.connection.query(Cypher.deleteReport, ["reportId": .string("rescan")])
    #expect(try store.linkSameMeasurements() == 0)
    try store.omopTransform()
    #expect(try store.run("duplicates").isEmpty)
  }
}

/// Port of the year-of-birth tests in tests/test_health_graph.py.
@Suite("Year of birth and sex", .serialized)
struct PatientAttributeTests {
  @Test func yearOfBirthAndSexReachPatientAndOmop() throws {
    var bundle = try Fixtures.bundle(Fixtures.golden)
    bundle["entry"] = ((bundle["entry"] as? [JSONObject]) ?? []).map { entry in
      guard var resource = entry["resource"] as? JSONObject, resource["resourceType"] as? String == "Patient"
      else { return entry }
      resource["birthDate"] = "1971-05-03"  // a full date is cut to the year
      resource["gender"] = "male"
      return ["resource": resource]
    }
    let parsed = try FHIR.parseBundle(bundle)
    #expect(parsed.patient == ["birthYear": .int(1971), "gender": .string("male")])
    let store = try HealthStore(path: Fixtures.tempStore())
    try store.initSchema()
    try store.importReport(parsed)
    try store.omopTransform()
    let p = try store.rows(cypher: "MATCH (p:Patient) RETURN p.birthYear AS y, p.gender AS g, p.birthDate AS d")
    #expect(p.first?["y"] == "1971" && p.first?["g"] == "male" && p.first?["d"] == "")
    let op = try store.rows(cypher: "MATCH (op:OMOPPerson) RETURN op.yearOfBirth AS y, op.genderConceptId AS g")
    #expect(op.first?["y"] == "1971" && op.first?["g"] == "8507")
  }

  @Test func withoutTheSwitchNothingAboutThePersonIsStored() throws {
    #expect(try FHIR.parseBundle(Fixtures.bundle(Fixtures.golden)).patient.isEmpty)
  }
}

@Suite("Knowledge layer", .serialized)
struct KnowledgeTests {
  /// Same counts as the Python seed: 6 risks, 4 scores, 55 marker links, 173 ranges,
  /// 48 studies (21 seeded with the risk links and newer views, 27 range sources), 10 risk links.
  @Test func seedsTheSameKnowledgeAsPython() throws {
    let store = try HealthStore(path: Fixtures.tempStore())
    try store.initSchema()
    try store.seedKnowledge()
    #expect(try store.count("HealthRisk") == 6)
    #expect(try store.count("RiskScore") == 4)
    #expect(try store.count("ReferenceRange") == 173)
    let markers = try store.rows(cypher: "MATCH (:LoincCode)-[k:MARKER_OF]->(:HealthRisk) RETURN count(k) AS n")
    #expect(markers.first?["n"] == "55")
    #expect(try store.count("Study") == 48)  // 21 for risk links and newer views, 27 behind the ranges
    let links = try store.rows(cypher: "MATCH (:HealthRisk)-[k:RAISES_RISK_OF]->(:HealthRisk) RETURN count(k) AS n")
    #expect(links.first?["n"] == "10")
    let examines = try store.rows(cypher: "MATCH (:Study)-[k:EXAMINES]->(:LoincCode) RETURN count(k) AS n")
    #expect(examines.first?["n"] == "115")
    let about = try store.rows(cypher: "MATCH (:Study {id: 'esc-eas-2025-lipids'})-[k:ABOUT]->(:HealthRisk) RETURN count(k) AS n")
    #expect(about.first?["n"] == "1")
    let sourced = try store.rows(cypher: "MATCH (:ReferenceRange)-[k:SOURCED_FROM]->(:Study) RETURN count(k) AS n")
    #expect(sourced.first?["n"] == "173")
  }

  @Test func seedingTwiceChangesNothing() throws {
    let store = try HealthStore(path: Fixtures.tempStore())
    try store.initSchema()
    #expect(try !store.seedKnowledge().isEmpty)
    #expect(try store.seedKnowledge().isEmpty)
    #expect(try store.count("ReferenceRange") == 173)
  }
}
