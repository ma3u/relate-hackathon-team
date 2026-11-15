import Foundation
import Relate

/// Assessments, as `health_graph/assessment.py` defines them: what a reading of the values and the
/// answers concluded (treated values, a misread value, a disagreement between watch and answer, what
/// to ask the doctor), each finding linked to the Observations, health risks and protocol responses it
/// rests on. The rules and the Cypher are generated from the Python (AssessmentRules, Cypher.swift).
public enum Assessments {
  /// The assessment checked and normalised; `HealthGraphError.invalid` names the first problem.
  public static func validate(_ assessment: JSONObject, riskIds: Set<String>? = nil) throws -> JSONObject {
    func fail(_ s: String) -> HealthGraphError { .invalid(s) }
    let title = (assessment["title"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let summary = (assessment["summary"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    guard !title.isEmpty, title.count <= AssessmentRules.maxTitle else {
      throw fail("title: 1 to \(AssessmentRules.maxTitle) characters")
    }
    guard summary.count <= AssessmentRules.maxSummary else {
      throw fail("summary: at most \(AssessmentRules.maxSummary) characters")
    }
    guard let findings = assessment["findings"] as? [Any], (1...AssessmentRules.maxFindings).contains(findings.count)
    else { throw fail("findings: a list of 1 to \(AssessmentRules.maxFindings)") }
    let protocols = assessment["protocols"] ?? [String]()
    guard let protocolIds = protocols as? [String] else { throw fail("protocols: a list of protocol ids") }
    var out: [JSONObject] = []
    for (i, any) in findings.enumerated() {
      let n = i + 1
      guard let f = any as? JSONObject else { throw fail("finding \(n): an object") }
      let kind = f["kind"] as? String ?? "", severity = f["severity"] as? String ?? "info"
      guard AssessmentRules.kinds[kind] != nil else {
        throw fail("finding \(n): kind '\(kind)' not among \(AssessmentRules.kindOrder)")
      }
      guard AssessmentRules.severities.contains(severity) else {
        throw fail("finding \(n): severity '\(severity)' not among \(AssessmentRules.severities)")
      }
      let ftitle = (f["title"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      let text = (f["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !ftitle.isEmpty, ftitle.count <= AssessmentRules.maxTitle else {
        throw fail("finding \(n): title of 1 to \(AssessmentRules.maxTitle) characters")
      }
      guard text.count <= AssessmentRules.maxText else {
        throw fail("finding \(n): text of at most \(AssessmentRules.maxText) characters")
      }
      guard let observations = (f["observations"] ?? [String]()) as? [String], !observations.contains(where: \.isEmpty)
      else { throw fail("finding \(n): observations are Observation resourceIds (strings)") }
      guard let risks = (f["risks"] ?? [String]()) as? [String], !risks.contains(where: \.isEmpty)
      else { throw fail("finding \(n): risks are health risk ids (strings)") }
      if let riskIds {
        let bad = risks.filter { !riskIds.contains($0) }
        if !bad.isEmpty { throw fail("finding \(n): unknown risks \(bad); known: \(riskIds.sorted())") }
      }
      out.append(["order": n, "kind": kind, "severity": severity, "title": ftitle, "text": text,
                  "observations": unique(observations), "risks": unique(risks)])
    }
    return ["title": title, "summary": summary, "protocols": unique(protocolIds), "findings": out]
  }

  static func unique(_ xs: [String]) -> [String] {
    var seen = Set<String>()
    return xs.filter { seen.insert($0).inserted }
  }
}

extension HealthStore {
  /// The health risk ids the knowledge layer holds.
  func healthRiskIds() throws -> Set<String> {
    Set(try connection.query("MATCH (h:HealthRisk) RETURN h.id AS id").records.compactMap { $0["id"]?.stringValue })
  }

  /// Stores one assessment, its findings linked to their values, risks and the newest response of
  /// each protocol it read. Returns the counts, with the observations it could not link.
  @discardableResult
  public func storeAssessment(_ assessment: JSONObject, source: String = "claude", authored: String? = nil)
    throws -> JSONObject
  {
    let risks = try healthRiskIds()
    let a = try Assessments.validate(assessment, riskIds: risks.isEmpty ? nil : risks)
    let authored = authored ?? ISO8601DateFormatter().string(from: Date())
    let patient = try singlePatient()
    let id = "\(patient)|assessment|\(authored)|\(UUID().uuidString.prefix(12).lowercased())"
    let findings = a.objects("findings")
    let asked = findings.reduce(0) { $0 + (($1["observations"] as? [String])?.count ?? 0) }
    return try connection.transaction { c in
      let stored = try c.query(Cypher.assessmentStore, [
        "patientId": .string(patient), "assessmentId": .string(id), "authored": .string(authored),
        "source": .string(source), "title": JSON.cypher(a["title"]), "summary": JSON.cypher(a["summary"]),
        "findings": JSON.cypher(findings),
      ])
      guard (stored.records.first?["findings"]?.intValue ?? 0) > 0 else {
        throw HealthGraphError.invalid("no person \(patient) in the graph")
      }
      let about = try c.query(Cypher.assessmentStoreAbout, ["assessmentId": .string(id), "findings": JSON.cypher(findings)])
      let linkedRisks = try c.query(Cypher.assessmentStoreRisks, ["assessmentId": .string(id), "findings": JSON.cypher(findings)])
      let based = try c.query(Cypher.assessmentStoreBasedOn, ["assessmentId": .string(id), "protocols": JSON.cypher(a["protocols"])])
      let linked = Int(about.records.first?["links"]?.intValue ?? 0)
      return [
        "id": id, "title": a["title"] ?? "", "findings": findings.count, "observations": linked,
        "unlinkedObservations": asked - linked, "risks": Int(linkedRisks.records.first?["links"]?.intValue ?? 0),
        "basedOn": Int(based.records.first?["links"]?.intValue ?? 0),
      ]
    }
  }
}
