import Foundation
import Relate

/// Anamnesis from the person's own data, as `health_graph/anamnesis.py` builds it:
/// the findings in the graph (newest values outside the guideline range valid on
/// their date, FIB-4, the exercise test, blood oxygen, a score input only the
/// person knows), what the graph already answers, and only the questions left.
/// The rules, questions and Cypher are generated from the Python
/// (AnamnesisData.swift, Cypher.swift); this file is the port of `plan()` and of
/// storing the answers.
public enum Anamnesis {
  nonisolated(unsafe) static let data: JSONObject = (try? JSON.object(Data(AnamnesisData.json.utf8))) ?? [:]
  static var groups: [JSONObject] { data.objects("groups") }
  static var items: [JSONObject] { data.objects("items") }
  static var rules: [JSONObject] { data.objects("rules") }
  static var questionnaire: JSONObject { data.object("questionnaire") ?? [:] }
  static var limits: JSONObject { data.object("limits") ?? [:] }
  static func item(_ id: String) -> JSONObject? { items.first { $0.string("linkId") == id } }
  static func rule(_ id: String) -> JSONObject? { rules.first { $0.string("id") == id } }

  static func double(_ any: Any?) -> Double? { (any as? NSNumber)?.doubleValue }

  /// Days from `a` to `b` (both YYYY-MM-DD or longer ISO strings).
  static func days(_ a: String, _ b: String) -> Int {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(identifier: "UTC")
    f.dateFormat = "yyyy-MM-dd"
    guard let x = f.date(from: String(a.prefix(10))), let y = f.date(from: String(b.prefix(10))) else { return 0 }
    return Int((y.timeIntervalSince(x) / 86_400).rounded())
  }

  static func isoDay(_ date: Date) -> String {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(identifier: "UTC")
    f.dateFormat = "yyyy-MM-dd"
    return f.string(from: date)
  }

  static func flag(_ value: Double, _ low: Double?, _ high: Double?) -> String {
    let near = double(limits["near"]) ?? 0.05
    if let high, value > high { return "high" }
    if let low, value < low { return "low" }
    if let high, high > 0, value >= high * (1 - near) { return "at_limit" }
    if let low, low > 0, value <= low * (1 + near) { return "at_limit_low" }
    return "ok"
  }

  /// One analyte's newest value judged against the guideline (else the lab's) range.
  static func judge(_ row: JSONObject, today: String) -> JSONObject {
    let value = double(row["value"]) ?? 0
    let gLow = double(row["low"]), gHigh = double(row["high"])
    let labLow = double(row["labLow"]), labHigh = double(row["labHigh"])
    let guideline = gLow != nil || gHigh != nil
    let (low, high) = guideline ? (gLow, gHigh) : (labLow, labHigh)
    var out: JSONObject = [:]
    for k in ["group", "code", "display", "value", "unit", "date"] { out[k] = row[k] ?? NSNull() }
    out["ageDays"] = days(row.string("date") ?? today, today)
    out["range"] = [
      "low": low as Any? ?? NSNull(), "high": high as Any? ?? NSNull(),
      "basis": guideline ? "guideline" : "lab",
      "source": guideline ? (row["source"] ?? NSNull()) : "the lab's printed range",
    ] as JSONObject
    let f = (low != nil || high != nil) ? flag(value, low, high) : "no_range"
    out["flag"] = f
    let lab = guideline ? flag(value, labLow, labHigh) : f
    out["labFlag"] = lab
    if guideline && lab == "high" && f != "high" && f != "at_limit" { out["flagLabOnly"] = true }
    return out
  }

  /// FIB-4 from the FIB4 row: AST and ALT of one day, the nearest platelet count within 14 days.
  static func fib4(_ r: JSONObject) -> JSONObject? {
    let maxDays = (limits["fib4Days"] as? Int) ?? 14
    guard let date = r.string("date"), let age = double(r["age"]), age > 0,
      let ast = double(r["ast"]), let alt = double(r["alt"]), alt > 0
    else { return nil }
    let per: (String?) -> Double = { u in
      (u ?? "").lowercased().replacingOccurrences(of: "µ", with: "u") == "ukat/l" ? 60 : 1
    }
    let near = (r["platelets"] as? [Any] ?? []).compactMap { p -> (Int, Double)? in
      guard let pair = p as? [Any], pair.count == 2, let d = pair[0] as? String, let v = double(pair[1]), v > 0
      else { return nil }
      let gap = abs(days(d, date))
      return gap <= maxDays ? (gap, v) : nil
    }.min { $0.0 < $1.0 || ($0.0 == $1.0 && $0.1 < $1.1) }
    guard let near else { return nil }
    let a = ast * per(r.string("astUnit")), l = alt * per(r.string("altUnit"))
    let value = (age * a / (near.1 * l.squareRoot()) * 100).rounded() / 100
    return ["value": value, "date": date, "age": age, "ast": (a * 10).rounded() / 10,
            "alt": (l * 10).rounded() / 10, "platelets": near.1]
  }
}

/// Foundation value of a Cypher value (rows for the plan and for JSON).
func foundation(_ v: CypherValue) -> Any {
  switch v {
  case .null: return NSNull()
  case .bool(let b): return b
  case .int(let i): return Int(i)
  case .float(let d): return d
  case .string(let s): return s
  case .list(let items): return items.map(foundation)
  case .map(let m): return m.mapValues(foundation)
  default: return v.plain
  }
}

extension HealthStore {
  func objects(_ cypher: String, _ parameters: [String: CypherValue] = [:]) throws -> [JSONObject] {
    try connection.query(cypher, parameters).records.map { $0.mapValues(foundation) }
  }

  /// Findings in the person's data, what the graph already answers, and the questions to ask.
  public func anamnesisPlan(today: String? = nil) throws -> JSONObject {
    let today = today ?? Anamnesis.isoDay(Date())
    let oldDays = (Anamnesis.limits["oldDays"] as? Int) ?? 548
    let answerDays = (Anamnesis.limits["answerDays"] as? Int) ?? 365
    let base = ISO8601DateFormatter().date(from: today + "T00:00:00Z") ?? Date()
    let since1y = Anamnesis.isoDay(base.addingTimeInterval(-365 * 86_400))
    let since3y = Anamnesis.isoDay(base.addingTimeInterval(-3 * 365 * 86_400))

    let groupParam = CypherValue.list(Anamnesis.groups.map { g in
      .map(["id": .string(g.string("id") ?? ""), "codes": JSON.cypher(g["codes"])])
    })
    var values: [String: JSONObject] = [:]
    for row in try objects(Cypher.anamnesisFindings, ["groups": groupParam]) {
      if let g = row.string("group") { values[g] = Anamnesis.judge(row, today: today) }
    }
    let facts = try objects(Cypher.anamnesisFacts, ["since1y": .string(since1y), "since3y": .string(since3y)])
      .first ?? [:]
    var answered: [String: JSONObject] = [:]
    for row in try objects(Cypher.anamnesisAnswered) {
      if let key = row.string("key") { answered[key] = row }
    }

    var known: [(String, String)] = []
    if let abpm = facts.string("abpm") {
      known.append(("bp_measured", "24-hour blood pressure measurement on \(abpm)"))
    } else if let n = facts["officeBp"] as? Int, n >= 2 {
      known.append(("bp_measured", "\(n) blood pressure readings in the last year"))
    }
    if let n = facts["activeWeeks"] as? Int, n >= 8 {
      known.append(("activity_measured", "Apple Watch exercise minutes for \(n) weeks of the last year"))
    }
    if let n = facts["weights"] as? Int, n >= 3 {
      known.append(("weight_series",
                    "\(n) weights from \(facts.string("firstWeight") ?? "") to \(facts.string("lastWeight") ?? "")"))
    }
    if let d = facts.string("boneDensity") { known.append(("bone_density", "bone density scan on \(d)")) }
    let knownBy = Dictionary(known, uniquingKeysWith: { a, _ in a })
    let recent = answered.filter { _, a in
      guard let at = a.string("authored") else { return false }
      return Anamnesis.days(at, today) <= answerDays
    }

    var rechecks: [JSONObject] = []
    for g in Anamnesis.groups {
      guard let id = g.string("id"), let v = values[id], let age = v["ageDays"] as? Int, age > oldDays,
        let f = v.string("flag"), f != "ok", f != "no_range"
      else { continue }
      rechecks.append(["name": g.string("name") ?? id, "display": v["display"] ?? NSNull(),
                       "date": v["date"] ?? NSNull(), "flag": f, "ageDays": age])
    }

    var findings: [JSONObject] = []
    for rule in Anamnesis.rules {
      var hits: [JSONObject] = []
      var detail: JSONObject?
      switch rule.string("kind") {
      case nil:
        let when = rule["when"] as? [String] ?? []
        for gid in rule["groups"] as? [String] ?? [] {
          guard let v = values[gid], let age = v["ageDays"] as? Int, age <= oldDays else { continue }
          var f = (v["flagLabOnly"] as? Bool) == true ? "lab_high" : (v.string("flag") ?? "")
          if f == "at_limit_low" && when.contains("low") { f = "low" }
          if when.contains(f) {
            var hit = v
            hit["name"] = Anamnesis.groups.first { $0.string("id") == gid }?.string("name") ?? gid
            hit["trigger"] = f
            hits.append(hit)
          }
        }
      case "fib4":
        var computed = try objects(Cypher.anamnesisFib4).first.flatMap(Anamnesis.fib4)
        if computed == nil, let s = try objects(Cypher.anamnesisStoredFib4).first, let v = Anamnesis.double(s["value"]) {
          computed = ["value": (v * 100).rounded() / 100, "date": String((s.string("computedAt") ?? "").prefix(10)),
                      "stored": true, "band": s["band"] ?? NSNull()]
        }
        if var c = computed, let v = Anamnesis.double(c["value"]), v >= 1.30,
          Anamnesis.days(c.string("date") ?? today, today) <= oldDays
        {
          c["cutOffs"] = "below 1.30 rules fibrosis out, 2.67 and above rules it in (EASL; 2.0 instead of 1.30 from age 65)"
          detail = c
          hits = ["1920-8", "1742-6", "777-3"].map { ["code": $0] }
        }
      case "exercise_bp":
        if let r = try objects(Cypher.anamnesisExerciseBp).first, let v = Anamnesis.double(r["value"]),
          let d = r.string("date")
        {
          let limit: Double = (r.string("sex") ?? "").lowercased() == "female" ? 190 : 210
          if v >= limit && Anamnesis.days(d, today) <= 3 * 365 {
            detail = ["value": r["value"] ?? v, "unit": r["unit"] ?? NSNull(), "date": d, "limit": Int(limit)]
            hits = [["code": "87739-9"]]
          }
        }
      case "spo2":
        if let r = try objects(Cypher.anamnesisSpo2, ["since1y": .string(since1y)]).first,
          let low = r["low"] as? Int, low >= 2
        {
          detail = ["lowWeeks": low, "weeks": r["weeks"] ?? NSNull(), "lowest": r["lowest"] ?? NSNull()]
          hits = [["code": "59408-5"]]
        }
      case "missing_answer":
        if let answer = rule.string("answer"), recent[answer] == nil { detail = ["missing": answer] }
      default:
        break
      }
      if hits.isEmpty && detail == nil { continue }
      let missing = (rule["ifMissing"] as? [String: String] ?? [:]).sorted { $0.key < $1.key }
        .filter { values[$0.key] == nil }.map(\.value)
      let dates: [String] = hits.compactMap { $0.string("date") }
      let date: Any = dates.max() ?? detail?.string("date") ?? NSNull()
      let codes: [String] = Array(Set(hits.compactMap { $0.string("code") })).sorted()
      let tests: [String] = (rule["tests"] as? [String] ?? []) + missing
      var finding: JSONObject = [:]
      finding["id"] = rule.string("id") ?? ""
      finding["title"] = rule["title"] ?? ""
      finding["why"] = rule["why"] ?? ""
      finding["risks"] = rule["risks"] ?? [String]()
      finding["values"] = hits.filter { $0["group"] != nil }
      finding["detail"] = detail ?? NSNull()
      finding["codes"] = codes
      finding["date"] = date
      finding["tests"] = tests
      findings.append(finding)
    }

    var questions: [JSONObject] = [], skipped: [JSONObject] = [], seen = Set<String>()
    for f in findings {
      guard let fid = f.string("id"), let rule = Anamnesis.rule(fid) else { continue }
      let date = f.string("date")
      let codes = f["codes"] as? [String] ?? []
      for linkId in rule["questions"] as? [String] ?? [] {
        guard let item = Anamnesis.item(linkId), let text = item.string("text") else { continue }
        let dated = text.contains("{date}")
        let key = dated && date != nil ? "\(linkId)@\(date!)" : linkId
        if seen.contains(key) {
          if let i = questions.firstIndex(where: { $0.string("key") == key }) {
            var fs = questions[i]["findings"] as? [String] ?? []
            if !fs.contains(fid) { fs.append(fid) }
            questions[i]["findings"] = fs
            questions[i]["basedOn"] = Array(Set((questions[i]["basedOn"] as? [String] ?? []) + codes)).sorted()
          }
          continue
        }
        seen.insert(key)
        if let a = recent[key] {
          let labels = (a["labels"] as? [String] ?? []).joined(separator: ", ")
          let extra = a.string("text").map { " / " + $0 } ?? ""
          skipped.append(["key": key, "linkId": linkId, "finding": fid,
                          "reason": "answered on \(String((a.string("authored") ?? "").prefix(10))): \(labels)\(extra)"])
          continue
        }
        if let by = item.string("knownBy"), let why = knownBy[by] {
          skipped.append(["key": key, "linkId": linkId, "finding": fid, "reason": why])
          continue
        }
        let options = (item["options"] as? [[Any]] ?? []).map { o -> JSONObject in
          ["code": o[0], "label": o[1], "riskFactor": o[2]]
        }
        questions.append([
          "key": key, "linkId": linkId, "context": dated ? (date ?? "") : NSNull(),
          "text": text.replacingOccurrences(of: "{date}", with: date ?? "that day"),
          "options": options, "multiple": item["multiple"] ?? false, "risks": item["risks"] ?? [],
          "findings": [fid], "basedOn": codes,
        ])
      }
    }
    return [
      "asOf": today, "sex": facts["sex"] ?? NSNull(), "birthYear": facts["birthYear"] ?? NSNull(),
      "findings": findings, "known": known.map { ["fact": $0.0, "detail": $0.1] },
      "questions": questions, "skipped": skipped, "rechecks": rechecks,
    ]
  }

  /// Validates and stores one sitting's answers: `{key: code | [codes] | {codes, text,
  /// basedOn, findings, question}}`, key = linkId or linkId@date. A code that is not
  /// one of the question's options, or an unknown question, refuses the whole sitting.
  @discardableResult
  public func storeAnamnesis(_ answers: JSONObject, source: String = "chat", authored: String? = nil) throws
    -> [String: Int]
  {
    let authored = authored ?? ISO8601DateFormatter().string(from: Date())
    let checked = try Anamnesis.validate(answers)
    let rows = checked.rows, basedOnRows = checked.basedOnRows, factors = checked.riskFactors
    let q = Anamnesis.questionnaire
    let qid = q.string("id") ?? "klarbefund-anamnesis"
    let patient = try singlePatient()
    let responseId = "\(patient)|\(qid)|\(authored)"
    return try connection.transaction { c in
      _ = try c.query(Cypher.anamnesisSeed, [
        "id": .string(qid), "version": JSON.cypher(q["version"]), "title": JSON.cypher(q["title"]),
        "items": JSON.cypher(Anamnesis.data["itemRows"]),
      ])
      _ = try c.query(Cypher.anamnesisStoreResponse, [
        "patientId": .string(patient), "questionnaire": .string(qid), "responseId": .string(responseId),
        "authored": .string(authored), "source": .string(source), "answers": .list(rows),
      ])
      let linked = try c.query(Cypher.anamnesisStoreBasedOn, [
        "responseId": .string(responseId), "rows": .list(basedOnRows),
      ])
      return ["answers": rows.count, "riskFactors": factors,
              "basedOn": Int(linked.records.first?["links"]?.intValue ?? 0)]
    }
  }
}

extension Anamnesis {
  /// One sitting's answers, checked against the questions and ready for the graph.
  public struct Checked {
    public let rows: [CypherValue]
    public let basedOnRows: [CypherValue]
    public let riskFactors: Int
    public var count: Int { rows.count }
  }

  /// Checks answers without a store (the MCP helper does this before it hands them over).
  public static func validate(_ answers: JSONObject) throws -> Checked {
    var rows: [CypherValue] = []
    var factors = 0
    var basedOnRows: [CypherValue] = []
    for (key, value) in answers.sorted(by: { $0.key < $1.key }) {
      let parts = key.split(separator: "@", maxSplits: 1).map(String.init)
      let linkId = parts[0], context = parts.count > 1 ? parts[1] : nil
      guard let item = item(linkId) else {
        throw HealthGraphError.invalid("unknown question \(linkId)")
      }
      var codes: [String] = [], text: String?, basedOn: [String] = [], findings: [String] = []
      var question = (item.string("text") ?? "").replacingOccurrences(of: "{date}", with: context ?? "that day")
      switch value {
      case let s as String: codes = [s]
      case let a as [String]: codes = a
      case let o as JSONObject:
        codes = o["codes"] as? [String] ?? []
        text = o.text("text")
        basedOn = o["basedOn"] as? [String] ?? []
        findings = o["findings"] as? [String] ?? []
        if let q = o.text("question") { question = q }
      default: throw HealthGraphError.invalid("\(key): an answer is a code, a list of codes or an object")
      }
      let options = (item["options"] as? [[Any]] ?? []).compactMap { o -> (String, String, Bool)? in
        guard o.count == 3, let c = o[0] as? String, let l = o[1] as? String else { return nil }
        return (c, l, (o[2] as? Bool) ?? false)
      }
      let byCode = Dictionary(options.map { ($0.0, $0) }, uniquingKeysWith: { a, _ in a })
      if let bad = codes.first(where: { byCode[$0] == nil }) {
        throw HealthGraphError.invalid("\(key): \(bad) is not one of \(options.map(\.0))")
      }
      if codes.count > 1 && (item["multiple"] as? Bool) != true {
        throw HealthGraphError.invalid("\(key) takes one answer, got \(codes)")
      }
      if let bad = findings.first(where: { rule($0) == nil }) {
        throw HealthGraphError.invalid("\(key): unknown finding \(bad)")
      }
      if codes.isEmpty && text == nil { continue }
      let risk = codes.contains { byCode[$0]?.2 == true }
      if risk { factors += 1 }
      let row: [String: CypherValue] = [
        "key": .string(key), "linkId": .string(linkId), "context": context.map(CypherValue.string) ?? .null,
        "codes": .list(codes.map(CypherValue.string)),
        "labels": .list(codes.map { .string(byCode[$0]!.1) }),
        "text": text.map(CypherValue.string) ?? .null, "riskFactor": .bool(risk),
        "risks": JSON.cypher(item["risks"]), "basedOn": .list(basedOn.map(CypherValue.string)),
        "findings": .list(findings.map(CypherValue.string)), "question": .string(question),
      ]
      rows.append(.map(row))
      if !basedOn.isEmpty { basedOnRows.append(.map(row)) }
    }
    return Checked(rows: rows, basedOnRows: basedOnRows, riskFactors: factors)
  }
}
