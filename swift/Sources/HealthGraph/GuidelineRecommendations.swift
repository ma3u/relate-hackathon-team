import Foundation
import Relate

/// Recommendations of a German guideline, as `health_graph/guidelines.py` extracts them: one record per
/// recommendation box with its number, grade (⇑⇑ ⇑ ⇔ ⇓ ⇓⇓), direction, chapter, page, the lab values its
/// wording names (LOINC) and a SHA-256 of the wording. No guideline text: the publishers' imprints require
/// written consent to store it, so the artefact carries facts and the link to the publisher's PDF page.
///
/// `validate` refuses any field outside `GuidelineRules.recordFields`, long strings and unknown grades, so
/// an artefact that carries wording never reaches the graph. Same rules as `validate()` in guidelines.py.
public enum GuidelineRecommendations {
  /// (recommendation rows, mention rows) ready for the Cypher in `Cypher.guideline*`.
  public static func validate(_ artefact: JSONObject) throws -> (rows: [JSONObject], mentions: [JSONObject]) {
    func fail(_ s: String) -> HealthGraphError { .invalid(s) }
    guard artefact["schemaVersion"] as? String == GuidelineRules.schemaVersion else {
      throw fail("schemaVersion: expected \(GuidelineRules.schemaVersion)")
    }
    var versions: [String: Any] = [:]
    for g in (artefact["guidelines"] as? [JSONObject]) ?? [] where g["extracted"] as? Bool == true {
      if let id = g["id"] as? String { versions[id] = g["version"] ?? NSNull() }
    }
    guard let recs = artefact["recommendations"] as? [Any], recs.count <= 5000 else {
      throw fail("recommendations: a list of at most 5000")
    }
    let idRe = try NSRegularExpression(pattern: GuidelineRules.idPattern)
    let loincRe = try NSRegularExpression(pattern: GuidelineRules.loincPattern)
    let shaRe = try NSRegularExpression(pattern: "^[0-9a-f]{64}$")
    func matches(_ re: NSRegularExpression, _ s: String) -> Bool {
      re.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) != nil
    }
    func page(_ v: Any?) -> Bool {
      guard let v, !(v is NSNull) else { return true }
      guard let n = v as? Int, !(v is Bool) else { return false }
      return n > 0 && n < 10000
    }
    var rows: [JSONObject] = [], mentions: [JSONObject] = []
    for (i, any) in recs.enumerated() {
      let at = "recommendation \(i + 1)"
      guard let r = any as? JSONObject else { throw fail("\(at): an object") }
      let extra = Set(r.keys).subtracting(GuidelineRules.recordFields)
      guard extra.isEmpty else { throw fail("\(at): fields not allowed: \(extra.sorted())") }
      guard let rid = r["id"] as? String, matches(idRe, rid) else {
        throw fail("\(at): id '\(r["id"] ?? "")' is not <guideline>:<number>")
      }
      guard let gid = r["guidelineId"] as? String, let version = versions[gid], rid.hasPrefix("\(gid):") else {
        throw fail("\(rid): guideline '\(r["guidelineId"] ?? "")' is not an extracted guideline of this artefact")
      }
      let grade = r["grade"]
      if let g = grade as? String {
        guard GuidelineRules.grades.contains(g) || g == "?" else { throw fail("\(rid): grade '\(g)' unknown") }
      } else if !(grade == nil || grade is NSNull) {
        throw fail("\(rid): grade unknown")
      }
      for key in ["number", "type", "basis", "status", "strength", "direction", "gradeLetter", "section", "consensus"] {
        guard let v = r[key], !(v is NSNull) else { continue }
        guard let s = v as? String, s.count <= 40 else { throw fail("\(rid): \(key) must be a short string") }
      }
      let url = r["pdfUrl"] as? String
      if let url { guard url.hasPrefix("https://"), url.count <= 300 else { throw fail("\(rid): pdfUrl must be an https link") } }
      else if !(r["pdfUrl"] == nil || r["pdfUrl"] is NSNull) { throw fail("\(rid): pdfUrl must be an https link") }
      guard let sha = r["wordingSha256"] as? String, matches(shaRe, sha) else {
        throw fail("\(rid): wordingSha256 must be a SHA-256")
      }
      guard page(r["page"]), page(r["printedPage"]) else { throw fail("\(rid): page must be a page number") }
      let reasonsAny = r["reviewReasons"] ?? [String]()
      guard let reasons = (reasonsAny is NSNull ? [String]() : reasonsAny as? [String]), reasons.count <= 10,
        reasons.allSatisfy({ $0.count <= GuidelineRules.maxText })
      else { throw fail("\(rid): reviewReasons: at most 10 short reasons") }
      let linksAny = r["loinc"] ?? [Any]()
      guard let links = (linksAny is NSNull ? [Any]() : linksAny as? [Any]), links.count <= 60 else {
        throw fail("\(rid): loinc: a list")
      }
      for link in links {
        guard let l = link as? JSONObject, let code = l["code"] as? String, matches(loincRe, code),
          let term = l["term"] as? String, term.count <= 40
        else { throw fail("\(rid): loinc entries are {code, term}") }
        mentions.append(["id": rid, "code": code, "term": term])
      }
      let scoresAny = r["scores"] ?? [Any]()
      guard let scores = (scoresAny is NSNull ? [Any]() : scoresAny as? [Any]), scores.count <= 10 else {
        throw fail("\(rid): scores entries are {id, term}")
      }
      let scoreRe = try NSRegularExpression(pattern: "^[a-z0-9-]{1,30}$")
      for score in scores {
        guard let s = score as? JSONObject, let id = s["id"] as? String, matches(scoreRe, id),
          let term = s["term"] as? String, term.count <= 40
        else { throw fail("\(rid): scores entries are {id, term}") }
        mentions.append(["id": rid, "score": id, "term": term])
      }
      guard r["dissent"] == nil || r["dissent"] is NSNull || r["dissent"] is Bool else {
        throw fail("\(rid): dissent must be true or false")
      }
      let short = ((r["checks"] as? JSONObject)?["shortVersion"] as? String).flatMap { $0.count <= 40 ? $0 : nil }
      func value(_ key: String) -> Any { r[key] ?? NSNull() }
      rows.append([
        "id": rid, "guidelineId": gid, "register": register(of: gid), "version": version,
        "number": value("number"), "type": value("type"), "basis": value("basis"), "status": value("status"),
        "grade": value("grade"), "strength": value("strength"), "direction": value("direction"),
        "gradeLetter": value("gradeLetter"), "page": value("page"), "printedPage": value("printedPage"),
        "section": value("section"), "pdfUrl": url ?? NSNull(), "wordingSha256": sha,
        "needsReview": (r["needsReview"] as? Bool ?? false) || !reasons.isEmpty, "reviewReasons": reasons,
        "shortVersion": short ?? NSNull(), "consensus": value("consensus"),
        "dissent": r["dissent"] as? Bool ?? false,
      ])
    }
    return (rows, mentions)
  }

  /// The register number as the knowledge layer writes it (evidence.GUIDELINES): "NVL 009", "AWMF 053-048".
  public static func register(of guidelineId: String) -> String {
    guidelineId.hasPrefix("nvl-") ? "NVL " + guidelineId.dropFirst(4) : "AWMF " + guidelineId
  }
}

extension HealthStore {
  /// Stores the recommendations of an artefact, each on its guideline (register and version), with a
  /// MENTIONS link to the LOINC codes its wording names. A guideline version the knowledge layer does not
  /// know is skipped and counted as `unmatched`. Recommendations no longer in a guideline's artefact go.
  @discardableResult
  public func storeGuidelineRecommendations(_ artefact: JSONObject, checkedAt: String? = nil) throws -> JSONObject {
    let (rows, mentions) = try GuidelineRecommendations.validate(artefact)
    let known = Set(try connection.query(Cypher.guidelineVersions).records.compactMap { r -> String? in
      guard let reg = r["register"]?.stringValue, let v = r["version"]?.stringValue else { return nil }
      return "\(reg)|\(v)"
    })
    let matched = rows.filter { known.contains("\($0["register"] as? String ?? "")|\($0["version"] as? String ?? "")") }
    let ids = Set(matched.compactMap { $0["id"] as? String })
    var byGuideline: [String: [String]] = [:]
    for r in matched { byGuideline[r["guidelineId"] as? String ?? "", default: []].append(r["id"] as? String ?? "") }
    let checkedAt = checkedAt ?? artefact["generatedAt"] as? String ?? ISO8601DateFormatter().string(from: Date())
    return try connection.transaction { c in
      let pruned = try c.query(Cypher.guidelinePruneRecommendations, [
        "guidelines": JSON.cypher(byGuideline.sorted { $0.key < $1.key }.map { ["id": $0.key, "ids": $0.value] }),
      ])
      let stored = try c.query(Cypher.guidelineStoreRecommendations, [
        "recommendations": JSON.cypher(matched), "checkedAt": .string(checkedAt),
      ])
      _ = try c.query(Cypher.guidelineUnlinkMentions, ["ids": JSON.cypher(ids.sorted())])
      let mine = mentions.filter { ids.contains($0["id"] as? String ?? "") }
      let linked = try c.query(Cypher.guidelineStoreMentions, [
        "mentions": JSON.cypher(mine.filter { $0["code"] != nil }),
      ])
      let scored = try c.query(Cypher.guidelineStoreScores, [
        "mentions": JSON.cypher(mine.filter { $0["score"] != nil }),
      ])
      return [
        "recommendations": Int(stored.records.first?["recommendations"]?.intValue ?? 0),
        "mentions": Int(linked.records.first?["mentions"]?.intValue ?? 0),
        "scores": Int(scored.records.first?["scores"]?.intValue ?? 0),
        "pruned": Int(pruned.records.first?["pruned"]?.intValue ?? 0),
        "unmatched": rows.count - matched.count,
      ]
    }
  }
}
