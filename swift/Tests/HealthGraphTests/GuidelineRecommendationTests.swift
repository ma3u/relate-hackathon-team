import Foundation
import Testing

@testable import HealthGraph

/// Port of tests/test_guidelines.py's graph tests: a guideline artefact carries facts, never wording,
/// and its recommendations hang on their guideline with a link to the lab values they name.
@Suite("Guideline recommendations", .serialized)
struct GuidelineRecommendationTests {
  static func store() throws -> HealthStore {
    let (store, _) = try Fixtures.loadedStore()
    try store.seedKnowledge()
    return store
  }

  static func artefact(_ override: JSONObject = [:], version: String = "1.0") -> JSONObject {
    var rec: JSONObject = [
      "id": "nvl-009:3-1", "guidelineId": "nvl-009", "number": "3-1", "type": "recommendation",
      "basis": "evidence", "status": "neu 2023", "grade": "⇑⇑", "strength": "soll", "direction": "do",
      "gradeLetter": "A", "page": 22, "printedPage": 22, "section": "3.2",
      "pdfUrl": "https://www.leitlinien.de/themen/hypertonie/langfassung/x.pdf#page=22",
      "wordingSha256": String(repeating: "0", count: 64),
      "loinc": [["code": "62238-1", "term": "eGFR"], ["code": "2823-3", "term": "Kalium"]],
      "checks": ["verbatim": true, "gate": true, "shortVersion": "same"], "needsReview": false, "reviewReasons": [String](),
    ]
    for (k, v) in override { rec[k] = v }
    return ["schemaVersion": GuidelineRules.schemaVersion, "generatedAt": "2026-11-27T12:00:00+00:00",
            "guidelines": [["id": "nvl-009", "version": version, "extracted": true]], "recommendations": [rec]]
  }

  @Test func anArtefactWithWordingIsRefused() throws {
    #expect(throws: (any Error).self) { try GuidelineRecommendations.validate(Self.artefact(["wording": "Der Test soll erfolgen."])) }
    #expect(throws: (any Error).self) {
      try GuidelineRecommendations.validate(Self.artefact(["reviewReasons": [String(repeating: "x", count: 200)]]))
    }
    #expect(throws: (any Error).self) { try GuidelineRecommendations.validate(Self.artefact(["grade": "Z"])) }
    #expect(throws: (any Error).self) { try GuidelineRecommendations.validate(Self.artefact(["id": "nvl-009 3-1"])) }
    #expect(throws: (any Error).self) {
      try GuidelineRecommendations.validate(Self.artefact(["loinc": [["code": "eGFR", "term": "eGFR"]]]))
    }
    let (rows, mentions) = try GuidelineRecommendations.validate(Self.artefact())
    #expect(rows.first?["register"] as? String == "NVL 009" && mentions.count == 2)
  }

  @Test func theInboxStoresRecommendationsOnTheirGuideline() throws {
    let store = try Self.store()
    let inbox = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
    let file = inbox.appendingPathComponent("1-nvl\(AnamnesisInbox.guidelinesSuffix)")
    try JSONSerialization.data(withJSONObject: Self.artefact()).write(to: file)
    #expect(AnamnesisInbox.waiting(try FileManager.default.contentsOfDirectory(atPath: inbox.path)))
    #expect(AnamnesisInbox.apply(from: inbox, to: store)
      == ["Guidelines: 1 recommendations stored, 2 links to lab values, 0 for a version not in the graph"])
    let row = try store.rows(cypher: """
      MATCH (g:Study)-[:HAS_RECOMMENDATION]->(e:GuidelineRecommendation)-[m:MENTIONS]->(c:LoincCode)
      RETURN g.register AS reg, e.grade AS grade, c.code AS code, m.term AS term
      """)
    // both codes are in the knowledge layer; a code nothing else knows is not created
    #expect(row.contains(["reg": "NVL 009", "grade": "⇑⇑", "code": "62238-1", "term": "eGFR"]))
  }

  @Test func storingAgainPrunesAndAnUnknownVersionWaits() throws {
    let store = try Self.store()
    try store.storeGuidelineRecommendations(Self.artefact())
    try store.storeGuidelineRecommendations(Self.artefact(["id": "nvl-009:3-2", "number": "3-2", "loinc": [Any]()]))
    #expect(try store.rows(cypher: "MATCH (e:GuidelineRecommendation) RETURN e.id AS id") == [["id": "nvl-009:3-2"]])
    let counts = try store.storeGuidelineRecommendations(Self.artefact(version: "2.0"))
    #expect(counts["unmatched"] as? Int == 1 && counts["recommendations"] as? Int == 0)
  }

  @Test func aDegamLetterGradeAndItsRiskScoreAreStored() throws {
    let store = try Self.store()
    var a = Self.artefact([
      "id": "053-024:9.1-2a", "guidelineId": "053-024", "number": "9.1-2a", "grade": "A", "strength": "soll",
      "gradeLetter": "A", "consensus": "starker Konsens", "dissent": true, "loinc": [Any](),
      "scores": [["id": "score2", "term": "kardiovaskuläres Risiko"]],
    ], version: "2.3")
    a["guidelines"] = [["id": "053-024", "version": "2.3", "extracted": true]]
    let counts = try store.storeGuidelineRecommendations(a)
    #expect(counts["recommendations"] as? Int == 1 && counts["scores"] as? Int == 1)
    let row = try store.rows(cypher: """
      MATCH (g:Study {register: 'AWMF 053-024'})-[:HAS_RECOMMENDATION]->(e)-[:MENTIONS]->(s:RiskScore)
      RETURN e.grade AS grade, toString(e.dissent) AS dissent, s.id AS score
      """)
    #expect(row == [["grade": "A", "dissent": "true", "score": "score2"]])
    #expect(throws: (any Error).self) {
      try GuidelineRecommendations.validate(Self.artefact(["scores": [["id": "SCORE 2!", "term": "x"]]]))
    }
  }

  @Test func theCypherIsThePythonReference() throws {
    let python = try String(contentsOf: Fixtures.root.appendingPathComponent("health_graph/guidelines.py"), encoding: .utf8)
    func squash(_ s: String) -> String { s.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
    for statement in [Cypher.guidelineVersions, Cypher.guidelinePruneRecommendations, Cypher.guidelineStoreRecommendations,
                      Cypher.guidelineUnlinkMentions, Cypher.guidelineStoreMentions, Cypher.guidelineStoreScores] {
      #expect(squash(python).contains(squash(statement)))
    }
  }

  @Test func theThreeDViewDescribesARecommendationWithoutWording() throws {
    let (group, name, lines) = Graph3D.describe("GuidelineRecommendation", [
      "register": "NVL 009", "number": "3-1", "grade": "⇑⇑", "strength": "soll", "direction": "do",
      "section": "3.2", "printedPage": 22, "basis": "evidence", "status": "neu 2023",
      "guidelineTitle": "Nationale VersorgungsLeitlinie Hypertonie", "guidelineVersion": "1.0",
    ])
    #expect(group == "Recommendation" && name == "NVL 009 · 3-1 ⇑⇑ soll")
    #expect(lines.filter { !$0.isEmpty } == ["Recommends doing it", "Chapter 3.2, page 22", "Evidence-based", "neu 2023",
                      "Nationale VersorgungsLeitlinie Hypertonie, version 1.0"])
  }

  /// Port of tests/test_norway.py: a Norwegian recommendation and a German box meet at a clinical question.
  @Test func norwegianAndGermanAnswersMeetAtTheQuestion() throws {
    let store = try Self.store()
    let norway: JSONObject = [
      "schemaVersion": GuidelineRules.schemaVersion, "generatedAt": "2026-11-28T12:00:00+00:00",
      "guidelines": [["id": "hdir-hjerte-kar", "version": "2024-12-05", "extracted": true]],
      "recommendations": [[
        "id": "hdir-hjerte-kar:0006-0002-a2", "guidelineId": "hdir-hjerte-kar", "number": "0006-0002-a2",
        "type": "recommendation", "grade": "sterk", "strength": "strong", "direction": "do not",
        "wordingSha256": String(repeating: "0", count: 64), "loinc": [["code": "10835-7", "term": "Lp(a)"]],
        "questions": ["q-lpa-measurement"], "codes": [["system": "SNOMED-CT", "code": "414916001"]],
      ]],
    ]
    let german = Self.artefact([
      "id": "053-024:7-2", "guidelineId": "053-024", "number": "7-2", "grade": "B", "direction": "do not",
      "loinc": [Any](), "questions": ["q-lpa-measurement"],
    ])
    var g = german
    g["guidelines"] = [["id": "053-024", "version": "2.3", "extracted": true]]
    let n = try store.storeGuidelineRecommendations(norway)
    _ = try store.storeGuidelineRecommendations(g)
    #expect(n["recommendations"] as? Int == 1 && n["answers"] as? Int == 1 && n["unmatched"] as? Int == 0)
    let rows = try store.rows(cypher: """
      MATCH (q:ClinicalQuestion {id: 'q-lpa-measurement'})<-[:ANSWERS]-(e:GuidelineRecommendation)
            <-[:HAS_RECOMMENDATION]-(s:Study)
      RETURN s.country AS country, s.licenceClass AS licence, e.direction AS dir
      ORDER BY country
      """)
    #expect(rows == [["country": "DE", "licence": "permission", "dir": "do not"],
                     ["country": "NO", "licence": "open", "dir": "do not"]])
    let reasons = try store.rows(cypher: """
      MATCH (q:ClinicalQuestion) RETURN q.id AS id, size(q.reasons) AS n ORDER BY id
      """)
    #expect(reasons.contains(["id": "q-statin-over-75", "n": "0"]))
    #expect(GuidelineRecommendations.register(of: "hdir-hjerte-kar") == "HDIR hjerte-kar")
  }

  @Test func badQuestionsAndCodesAreRefused() throws {
    #expect(throws: (any Error).self) { try GuidelineRecommendations.validate(Self.artefact(["questions": ["statins"]])) }
    #expect(throws: (any Error).self) {
      try GuidelineRecommendations.validate(Self.artefact(["codes": [["system": "LOINC", "code": "1-1"]]]))
    }
    let (_, mentions) = try GuidelineRecommendations.validate(Self.artefact(["questions": ["q-ldl-target", "q-ldl-target"]]))
    #expect(mentions.filter { $0["question"] != nil }.count == 1)
  }
}
