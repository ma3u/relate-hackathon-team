import Foundation
import Relate

/// Anamnesis protocols, as `health_graph/protocols.py` defines them: validated questionnaires
/// (Life's Essential 8, FINDRISC, AUDIT-C, MEDAS-14, PHQ-2) and structured history (tobacco,
/// family history, lipid-lowering medication, eating pattern), each question with its LOINC code
/// and each answer with the SNOMED CT concept it asserts, in their own category in the graph.
/// The definitions and the Cypher are generated from the Python (ProtocolData.swift,
/// Cypher.swift); this seeds them, and checks, scores and stores answers the same way.
public enum Protocols {
  nonisolated(unsafe) static let data: JSONObject = (try? JSON.object(Data(ProtocolData.json.utf8))) ?? [:]
  static var definitions: [JSONObject] { data.objects("protocols") }
  public static var ids: [String] { definitions.compactMap { $0.string("id") } }
  static func definition(_ id: String) -> JSONObject? { definitions.first { $0.string("id") == id } }
  static func items(_ p: JSONObject) -> [JSONObject] { p.objects("items") }
  static func options(_ item: JSONObject) -> [JSONObject] { item.objects("options") }
  static func points(_ o: JSONObject) -> Double? {
    guard JSON.number(o["points"]) != nil, let n = o["points"] as? NSNumber else { return nil }  // not null, not a Bool
    return n.doubleValue
  }
  static func option(_ item: JSONObject, _ code: String) -> JSONObject? { options(item).first { $0.string("code") == code } }

  /// The protocols as the graph holds them, with why and how each is scored: for Claude (anamnesis_protocols).
  public static func catalog() -> [JSONObject] {
    data.objects("rows").map { row in
      var out = row
      let p = definition(row.string("id") ?? "") ?? [:]
      for key in ["bands", "cutOff", "flagFrom", "flagBelow", "bandSnomed", "evidence"] where p[key] != nil {
        out[key] = p[key]
      }
      out["items"] = row.objects("items").map { item in
        item.filter { ["linkId", "text", "type", "multiple", "loinc", "snomed", "metric", "prefill", "enableWhen",
                       "options", "labels", "points", "optionSnomed"].contains($0.key) }
      }
      return out
    }
  }

  /// Whether a question applies, given the answers so far (`enableWhen`).
  static func enabled(_ item: JSONObject, _ answers: [String: [String]]) -> Bool {
    guard let cond = item.object("enableWhen") else { return true }
    for (link, want) in cond {
      let wants = (want as? [String]) ?? [(want as? String) ?? ""]
      if Set(answers[link] ?? []).isDisjoint(with: wants) { return false }
    }
    return true
  }

  /// The score so far, the range it can still reach, and its band once complete: the same
  /// rules as `protocols.score()` (published points summed, the LE8 average, the ESC family rule).
  public static func score(_ p: JSONObject, _ answers: [String: [String]], sex: String? = nil) -> JSONObject? {
    let method = p.string("method")
    if method == "family" { return familySummary(answers) }
    let shown = items(p).filter { enabled($0, answers) }
    var result: JSONObject
    switch method {
    case "sum":
      var got = 0.0, lo = 0.0, hi = 0.0
      var missing: [String] = []
      for it in shown {
        if let skip = it.object("skipIf"), skip.allSatisfy({ answers[$0.key]?.first == $0.value as? String }) { continue }
        let link = it.string("linkId") ?? "", pts = options(it).compactMap(points)
        if let code = answers[link]?.first {
          got += option(it, code).flatMap(points) ?? 0
        } else {
          missing.append(link)
          lo += pts.min() ?? 0
          hi += pts.max() ?? 0
        }
      }
      result = ["value": got, "min": got + lo, "max": got + hi, "missing": missing, "complete": missing.isEmpty]
    case "le8":
      var order: [String] = [], base: [String: Double] = [:], adjust: [String: Double] = [:]
      for it in shown {
        let metric = it.string("metric") ?? ""
        if !order.contains(metric) { order.append(metric) }
        guard let code = answers[it.string("linkId") ?? ""]?.first else { continue }
        let pts = option(it, code).flatMap(points) ?? 0
        if (it["adjust"] as? Bool) == true { adjust[metric, default: 0] += pts } else { base[metric] = pts }
      }
      var per: [String: Double] = [:]
      for (m, b) in base { per[m] = b == 0 ? 0 : max(0, b + (adjust[m] ?? 0)) }
      let missing = order.filter { per[$0] == nil }
      result = ["metrics": per, "missing": missing, "complete": missing.isEmpty]
      if !per.isEmpty {
        let sum = per.values.reduce(0, +)
        result["value"] = (sum / Double(per.count)).rounded(.toNearestOrEven)  // Python's round()
      }
    default:
      return nil
    }
    if let v = result["value"] as? Double, result["complete"] as? Bool == true {
      let (i, label, meaning) = band(p, v, sex: sex)
      result["band"] = label
      result["meaning"] = meaning
      result["flag"] = flagged(p, v, i)
      if let codes = p["bandSnomed"] as? [String], i < codes.count { result["snomed"] = codes[i] }
    }
    return result
  }

  static func band(_ p: JSONObject, _ value: Double, sex: String?) -> (Int, String, String) {
    let bands = p["bands"] as? [[Any]] ?? []
    var i = 0
    if let cut = p.object("cutOff") {
      let limit = ((cut[(sex ?? "any").lowercased()] ?? cut["any"]) as? NSNumber)?.doubleValue ?? .infinity
      i = value >= limit ? 1 : 0
    } else {
      for (k, b) in bands.enumerated() where value >= ((b.first as? NSNumber)?.doubleValue ?? 0) { i = k }
    }
    guard i < bands.count, bands[i].count == 3 else { return (i, "", "") }
    return (i, bands[i][1] as? String ?? "", bands[i][2] as? String ?? "")
  }

  static func flagged(_ p: JSONObject, _ value: Double, _ i: Int) -> Bool {
    if p["cutOff"] != nil { return i == 1 }
    if let f = (p["flagFrom"] as? NSNumber)?.doubleValue { return value >= f }
    if let f = (p["flagBelow"] as? NSNumber)?.doubleValue { return value < f }
    return false
  }

  /// The ESC 2021 reading of a family history: premature (men before 55, women before 65), later, or none.
  static func familySummary(_ answers: [String: [String]]) -> JSONObject? {
    let who = Set(answers["family-cvd-who"] ?? [])
    if who.isEmpty { return nil }
    let one = { (k: String) in answers[k]?.first }
    if who == ["none"] {
      return ["complete": true, "band": "none", "meaning": "no heart disease in parents or siblings",
              "snomed": "160270001", "flag": false, "derived": ["family-cvd": "no"]]
    }
    var early: [String] = []
    if who.contains("father") && one("family-cvd-father-age") == "<55" { early.append("father before 55") }
    if who.contains("mother") && one("family-cvd-mother-age") == "<65" { early.append("mother before 65") }
    let sibling = who.contains("brother") || who.contains("sister")
    if sibling && one("family-cvd-sibling-age") == "yes" { early.append("a brother or sister early") }
    if !early.isEmpty {
      let male = early.contains { $0.hasPrefix("father") || $0.hasPrefix("a brother") }
      return ["complete": true, "band": "premature", "flag": true,
              "meaning": "premature heart disease in the family (" + early.joined(separator: ", ")
                + "): an ESC 2021 risk modifier",
              "snomed": male ? "439724007" : "438825005", "derived": ["family-cvd": "yes"]]
    }
    let unknown = (who.contains("father") && (one("family-cvd-father-age") ?? "unknown") == "unknown")
      || (who.contains("mother") && (one("family-cvd-mother-age") ?? "unknown") == "unknown")
      || (sibling && (one("family-cvd-sibling-age") ?? "unknown") == "unknown")
    if unknown || who == ["unknown"] {
      return ["complete": false, "band": "age unknown", "flag": false,
              "meaning": "the age at the first event decides whether it counts", "snomed": "266894000"]
    }
    return ["complete": true, "band": "later in life", "flag": false,
            "meaning": "heart disease in the family, but not early: not a risk modifier in ESC 2021",
            "snomed": "266894000", "derived": ["family-cvd": "no"]]
  }

  /// One protocol's answers, checked against its questions and ready for the graph.
  public struct Checked {
    public let protocolId: String
    public let rows: [JSONObject]
    public var count: Int { rows.count }
  }

  /// Checks answers without a store (the MCP helper and the inbox do this first): `{linkId: code |
  /// [codes] | {codes, text, prefilled, observation}}`. An unknown question, a code that is not one
  /// of its options or a month that is not YYYY-MM refuses them all.
  public static func validate(_ protocolId: String, _ answers: JSONObject) throws -> Checked {
    guard let p = definition(protocolId) else {
      throw HealthGraphError.invalid("unknown protocol \(protocolId); known: \(ids.joined(separator: ", "))")
    }
    var rows: [JSONObject] = []
    for (linkId, value) in answers.sorted(by: { $0.key < $1.key }) {
      guard let item = items(p).first(where: { $0.string("linkId") == linkId }) else {
        throw HealthGraphError.invalid("\(protocolId): unknown question \(linkId)")
      }
      var codes: [String] = [], text: String?, prefilled: String?, observation: String?
      switch value {
      case let s as String: codes = [s]
      case let a as [String]: codes = a
      case let o as JSONObject:
        codes = o["codes"] as? [String] ?? []
        text = o.text("text")
        prefilled = o.text("prefilled")
        observation = o.text("observation")
      default: throw HealthGraphError.invalid("\(linkId): an answer is a code, a list of codes or an object")
      }
      let question = item.string("text") ?? ""
      if item.string("type") == "month" {
        let month = String((text ?? codes.first ?? "").prefix(7))
        let parts = month.split(separator: "-")
        guard parts.count == 2, let y = Int(parts[0]), let m = Int(parts[1]), y > 1900, (1...12).contains(m) else {
          throw HealthGraphError.invalid("\(linkId): \(month) is not a year and month (YYYY-MM)")
        }
        rows.append(["linkId": linkId, "codes": [String](), "labels": [String](), "text": month,
                     "snomed": [String](), "points": NSNull(), "riskFactor": false, "question": question,
                     "prefilled": prefilled ?? NSNull(), "observation": observation ?? NSNull()])
        continue
      }
      if let bad = codes.first(where: { option(item, $0) == nil }) {
        throw HealthGraphError.invalid("\(linkId): \(bad) is not one of \(options(item).compactMap { $0.string("code") })")
      }
      if codes.count > 1 && (item["multiple"] as? Bool) != true {
        throw HealthGraphError.invalid("\(linkId) takes one answer, got \(codes)")
      }
      if codes.isEmpty && text == nil { continue }
      let chosen = codes.compactMap { option(item, $0) }
      let pts = chosen.compactMap(points)
      rows.append([
        "linkId": linkId, "codes": codes, "labels": chosen.compactMap { $0.string("label") },
        "text": text ?? NSNull(), "snomed": chosen.compactMap { $0.text("snomed") },
        "points": pts.isEmpty ? NSNull() : pts.reduce(0, +) as Any,
        "riskFactor": chosen.contains { ($0["riskFactor"] as? Bool) == true }, "question": question,
        "prefilled": prefilled ?? NSNull(), "observation": observation ?? NSNull(),
      ])
    }
    return Checked(protocolId: protocolId, rows: rows)
  }
}

extension HealthStore {
  /// Writes the anamnesis category, its protocols, questions and SNOMED CT codes; a no-op when current.
  @discardableResult
  public func seedProtocols(force: Bool = false) throws -> [String: Int] {
    let category = Protocols.data.object("category") ?? [:]
    let current = try connection.query(
      "MATCH (c:AnamnesisCategory {id: $id}) RETURN c.version AS v", ["id": JSON.cypher(category["id"])]
    ).records.first?["v"]?.plain
    if current == ProtocolData.version && !force { return [:] }
    let rows = Protocols.data.objects("rows")
    let itemRows = rows.flatMap { $0.objects("items") }
    return try connection.transaction { c in
      let codes = try c.query(Cypher.protocolSeedCategory, [
        "category": JSON.cypher(category), "snomed": JSON.cypher(Protocols.data["snomed"]),
        "version": .string(ProtocolData.version),
      ])
      let links = try c.query(Cypher.protocolSeedProtocols, [
        "categoryId": JSON.cypher(category["id"]), "protocols": JSON.cypher(rows),
      ])
      _ = try c.query(Cypher.protocolSeedLoinc, ["protocols": JSON.cypher(rows)])
      _ = try c.query(Cypher.protocolSeedSnomed, ["protocols": JSON.cypher(rows)])
      let answerCodes = try c.query(Cypher.protocolSeedItems, ["protocols": JSON.cypher(rows)])
      _ = try c.query(Cypher.protocolSeedItemLoinc, ["items": JSON.cypher(itemRows.filter { $0.text("loinc") != nil })])
      _ = try c.query(Cypher.protocolSeedItemSnomed, ["items": JSON.cypher(itemRows.filter { $0.text("snomed") != nil })])
      return [
        "protocols": rows.count, "items": itemRows.count,
        "snomedCodes": Int(codes.records.first?["codes"]?.intValue ?? 0),
        "riskLinks": Int(links.records.first?["links"]?.intValue ?? 0),
        "answerCodes": Int(answerCodes.records.first?["links"]?.intValue ?? 0),
      ]
    }
  }

  /// Checks, scores and stores one protocol's answers as a QuestionnaireResponse, each answer
  /// linked to the SNOMED CT concept it asserts and, when prefilled, to the value it was read from.
  @discardableResult
  public func storeProtocol(_ protocolId: String, _ answers: JSONObject, source: String = "chat",
                            authored: String? = nil) throws -> JSONObject
  {
    let authored = authored ?? ISO8601DateFormatter().string(from: Date())
    let checked = try Protocols.validate(protocolId, answers)
    guard let p = Protocols.definition(protocolId) else { throw HealthGraphError.invalid("unknown protocol") }
    try seedProtocols()
    let patient = try singlePatient()
    let sex = try connection.query("MATCH (p:Patient) RETURN p.gender AS g").records.first?["g"]?.stringValue
    var codes: [String: [String]] = [:]
    for r in checked.rows {
      if let c = r["codes"] as? [String], !c.isEmpty, let link = r.string("linkId") { codes[link] = c }
    }
    let result = Protocols.score(p, codes, sex: sex) ?? [:]
    let responseId = "\(patient)|\(protocolId)|\(authored)"
    let flag = result["flag"] as? Bool ?? false
    let derived: [JSONObject] = (result.object("derived") ?? [:]).compactMap { link, code in
      guard let code = code as? String else { return nil }
      return ["linkId": link, "codes": [code], "labels": [code == "yes" ? "Yes" : "No"], "riskFactor": code == "yes",
              "question": "Did a parent or sibling have heart disease early (men before 55, women before 65)?"]
    }
    return try connection.transaction { c in
      _ = try c.query(Cypher.protocolStoreResponse, [
        "patientId": .string(patient), "protocol": .string(protocolId), "responseId": .string(responseId),
        "authored": .string(authored), "status": .string((result["complete"] as? Bool ?? true) ? "completed" : "in-progress"),
        "source": .string(source), "score": JSON.cypher(result["value"]), "band": JSON.cypher(result["band"]),
        "meaning": JSON.cypher(result["meaning"]), "flag": .bool(flag), "answers": JSON.cypher(checked.rows),
      ])
      _ = try c.query(Cypher.protocolStoreAnswerCodes, [
        "responseId": .string(responseId),
        "rows": JSON.cypher(checked.rows.filter { !($0["snomed"] as? [String] ?? []).isEmpty }),
      ])
      let prefilled = checked.rows.filter { $0.text("observation") != nil }
      if !prefilled.isEmpty {
        _ = try c.query(Cypher.protocolStorePrefilledFrom, ["responseId": .string(responseId), "rows": JSON.cypher(prefilled)])
      }
      let responseCodes = [p.text("scoreSnomed"), result["snomed"] as? String].compactMap { $0 }
      _ = try c.query(Cypher.protocolStoreResponseLinks, [
        "responseId": .string(responseId), "snomed": JSON.cypher(responseCodes),
        "risks": flag ? JSON.cypher(p["risks"]) : .list([]),
      ])
      if !derived.isEmpty {
        _ = try c.query(Cypher.protocolStoreDerived, [
          "responseId": .string(responseId), "rows": JSON.cypher(derived), "authored": .string(authored),
          "protocol": .string(protocolId),
        ])
      }
      return ["answers": checked.count, "score": result["value"] ?? NSNull(), "band": result["band"] ?? NSNull(),
              "flag": flag, "derived": derived.count, "name": p.string("name") ?? protocolId]
    }
  }
}
