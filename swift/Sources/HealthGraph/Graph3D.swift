import Foundation
import Relate

/// The data of the 3D view (scripts/graph3d.html), built from a store the way `scripts/graph3d.py`
/// builds it: every node with its group, name and detail lines, every relationship, and the person's
/// anamnesis protocols. Klarbefund for Mac injects it into the bundled page; the terminal script does
/// the same for the vault.
///
/// Not yet here (the Python view has them): the published scores (SCORE2, eGFR, FIB-4, TyG, the
/// lipids beyond LDL) and protocol answers prefilled from lab and Apple Watch values. Protocol
/// answers are prefilled from the person's earlier answers and year of birth.
public enum Graph3D {
  /// Python's `num`: nothing for null, `%g` for a float, the number as written for an integer.
  static func num(_ v: Any?) -> String {
    switch v {
    case nil, is NSNull: return ""
    case let d as Double: return String(format: "%g", d)
    case let i as Int: return String(i)
    case let s as String: return s
    default: return "\(v!)"
    }
  }

  static func str(_ p: JSONObject, _ key: String) -> String? { nonEmpty(p[key] as? String) }

  /// (group, name, detail lines) for one node, as `describe()` in scripts/graph3d.py.
  static func describe(_ label: String, _ p: JSONObject) -> (String, String, [String]) {
    switch label {
    case "Observation":
      let device = p["sourceKind"] as? String == "device-weekly-mean"
      let name = str(p, "display") ?? str(p, "loincDisplay") ?? str(p, "code") ?? "Observation"
      let value = "\(str(p, "comparator") ?? "")\(num(p["valueQuantity"])) \(str(p, "unit") ?? "")"
        .trimmingCharacters(in: .whitespaces)
      var lines = [value, str(p, "effectiveDate") ?? str(p, "effectiveStart") ?? ""]
      if let c = str(p, "code") { lines.append("LOINC \(c)") }
      if !(p["referenceLow"] is NSNull || p["referenceLow"] == nil) || !(p["referenceHigh"] is NSNull || p["referenceHigh"] == nil) {
        lines.append("Lab range \(num(p["referenceLow"])) – \(num(p["referenceHigh"]))")
      } else if let t = str(p, "referenceText") {
        lines.append("Lab range \(t)")
      }
      if let t = str(p, "taxonDisplay") { lines.append(t) }
      if let s = str(p, "sourceLine") { lines.append("Source \(s)") }
      if str(p, "duplicateOf") != nil { lines.append("Also in another report") }
      return (device ? "Apple Watch week" : "Lab value", name, lines)
    case "DiagnosticReport":
      return (label, str(p, "title") ?? "Report", [str(p, "effectiveDate") ?? "", str(p, "performer") ?? ""])
    case "DocumentReference":
      return (label, str(p, "title") ?? "Document", [str(p, "created") ?? ""])
    case "Provenance":
      return (label, "Provenance: \(str(p, "activity") ?? "scan")", [str(p, "recorded") ?? ""])
    case "Organization":
      return (label, str(p, "name") ?? "Lab", [])
    case "Patient":
      return (label, "You", [])
    case "LoincCode":
      return (label, str(p, "display") ?? str(p, "code") ?? label, ["LOINC \(num(p["code"]))"])
    case "NcbiTaxon":
      return (label, str(p, "display") ?? str(p, "code") ?? label, ["NCBI \(num(p["code"]))"])
    case "ReferenceRange":
      let g = "\(num(p["guidelineLow"])) – \(num(p["guidelineHigh"])) \(str(p, "ucum") ?? "")"
      let o = "\(num(p["optimalLow"])) – \(num(p["optimalHigh"]))"
      var lines = ["Guideline \(g)".trimmingCharacters(in: .whitespaces), "Optimal \(o)", str(p, "sex") ?? "",
                   str(p, "sourceLabel") ?? "", str(p, "validFrom").map { "Valid from \($0)" } ?? ""]
      if let until = str(p, "validUntil") {
        lines.insert("Superseded on \(until): \(str(p, "supersededBy") ?? "")".trimmingCharacters(in: .whitespaces), at: 0)
      }
      return (label, "Range: \(str(p, "analyteKey") ?? num(p["loinc"]))", lines)
    case "HealthRisk":
      return (label, str(p, "name") ?? label, [str(p, "description") ?? ""])
    case "RiskScore":
      return (label, str(p, "name") ?? label, [str(p, "source") ?? ""])
    case "Knowledge":
      return (label, "Knowledge layer", [str(p, "rangesSource") ?? ""])
    case "Study":
      let cit = str(p, "citation") ?? ""
      let name: String
      if let r = cit.range(of: " (") {
        name = String(cit[..<r.lowerBound])
      } else {
        let first = cit.split(separator: ",", maxSplits: 1).first.map(String.init) ?? ""
        name = "\(first.replacingOccurrences(of: " et al.", with: "")) \(num(p["year"]))"
          .trimmingCharacters(in: .whitespaces)
      }
      let topics = (p["topics"] as? [String]) ?? []
      return (p["kind"] as? String == "guideline" ? "Guideline" : "Study", name, [
        str(p, "title") ?? "", cit, str(p, "design") ?? "",
        topics.isEmpty ? "" : "Topics: " + topics.joined(separator: ", "),
        str(p, "pmid").map { "PubMed \($0)" } ?? "",
      ] + evidenceLines(p))
    case "AnamnesisCategory", "AnamnesisProtocol", "Questionnaire":
      return ("Anamnesis protocol", str(p, "name") ?? str(p, "title") ?? label, [
        str(p, "title") ?? "", str(p, "source") ?? "", str(p, "why") ?? str(p, "description") ?? "",
        str(p, "pmid").map { "PubMed \($0)" } ?? "",
      ])
    case "ProtocolItem", "QuestionnaireItem":
      let labels = (p["labels"] as? [String]) ?? []
      return ("Protocol question", str(p, "text") ?? str(p, "linkId") ?? label, [
        str(p, "loinc").map { "LOINC \($0)" } ?? "", str(p, "snomed").map { "SNOMED CT \($0)" } ?? "",
        "Options: " + labels.joined(separator: ", "), str(p, "prefill").map { "Prefilled from \($0)" } ?? "",
      ])
    case "SnomedCode":
      return ("SNOMED code", str(p, "display") ?? num(p["code"]), ["SNOMED CT \(num(p["code"]))", str(p, "semanticTag") ?? ""])
    case "QuestionnaireResponse":
      let what = str(p, "protocol") ?? "anamnesis"
      let score = (p["score"] == nil || p["score"] is NSNull) ? "" : "score \(num(p["score"]))"
      return ("Your answer", "Your \(what) answers", [str(p, "authored") ?? "", score, str(p, "band") ?? "", str(p, "meaning") ?? ""])
    case "Answer":
      let labels = ((p["labels"] as? [String]) ?? []).joined(separator: ", ")
      return ("Your answer", "\(num(p["linkId"])): \(labels.isEmpty ? (str(p, "text") ?? "") : labels)", [
        str(p, "question") ?? "", str(p, "authored") ?? "", str(p, "prefilled").map { "Prefilled from \($0)" } ?? "",
      ])
    case "ScoreResult":  // your value of a risk score; the score itself is the RiskScore it hangs on
      let shown = (p["value"] as? Double).map { num(($0 * 100).rounded() / 100) } ?? num(p["value"])
      return (label, shown.isEmpty ? "Your result" : "Your result: \(shown)", [
        str(p, "band") ?? "", str(p, "note") ?? "", str(p, "computedAt") ?? "",
      ])
    case "OMOPPerson":
      return (label, "OMOP person", [])
    case "OMOPMeasurement":
      let value = "\(num(p["valueAsNumber"])) \(str(p, "unitSourceValue") ?? "")".trimmingCharacters(in: .whitespaces)
      return (label, str(p, "measurementSourceValue") ?? "OMOP measurement", [value, str(p, "measurementDate") ?? ""])
    default:
      return (label, label, [])
    }
  }

  static func isNumber(_ v: Any?) -> Bool { v is Int || v is Double }
  static func double(_ v: Any?) -> Double? { (v as? Double) ?? (v as? Int).map(Double.init) }

  /// `evidence_lines()` in scripts/graph3d.py: a German guideline's validity and where it is behind,
  /// a study's publication status and appraisal (health_graph/evidence.py).
  static func evidenceLines(_ p: JSONObject) -> [String] {
    var lines: [String] = []
    func list(_ k: String) -> [String] { (p[k] as? [String]) ?? [] }
    if let adopted = str(p, "adoptedDate") {
      lines.append("\(str(p, "publisher") ?? "") \(str(p, "guidelineClass") ?? ""), version \(str(p, "version") ?? "")"
        .trimmingCharacters(in: .whitespaces))
      var valid = "Adopted \(adopted), valid until \(str(p, "validUntil") ?? "?")"
      if str(p, "validity") == "partly-expired" { valid += "; parts expired on \(str(p, "earliestValidUntil") ?? "")" }
      lines.append(valid)
      if p["evidenceMedianAge"] != nil && !(p["evidenceMedianAge"] is NSNull) {
        lines.append("Cited evidence: median \(num(p["evidenceMedianAge"])) years old on adoption, newest from "
          + "\(num(p["newestCitedYear"])), \(num(p["referencesCount"])) references")
      }
      lines += list("currency").map { "Behind: \($0)" }
    }
    if let status = str(p, "publicationStatus") {
      lines.append((status == "ok" ? "Status: no retraction, correction or concern" : "Status: \(status.uppercased())")
        + " (PubMed, checked \(str(p, "statusCheckedAt") ?? ""))")
    }
    if let passed = p["gatePassed"] as? Bool {
      if !passed {
        lines.append("Quality gate: not passed (" + list("gateReasons").joined(separator: "; ") + "), context only")
      } else if str(p, "gateStatus") == "provisional" {
        lines.append("Quality gate: form and precision passed, set against a guideline provisionally ("
          + list("gateOpen").joined(separator: "; ") + ")")
      } else {
        lines.append("Quality gate: passed, risk of bias judged by a person, may be set against a guideline")
      }
      if let precision = str(p, "gatePrecision") { lines.append("Precision: \(precision)") }
    }
    if let verdict = str(p, "appraisalVerdict") {
      lines += ["Question: \(str(p, "appraisalQuestion") ?? "")", "Verdict: \(verdict)",
                "Certainty: \(str(p, "certainty") ?? "")",
                "Checked by code: " + list("appraisalChecked").joined(separator: "; "),
                "Left to a person: " + list("appraisalOpen").joined(separator: "; "),
                "Appraised \(str(p, "appraisedAt") ?? ""): \(str(p, "appraisalSource") ?? "")"]
    }
    return lines
  }

  /// `build()` in scripts/graph3d.py: the nodes and links of the page.
  static func build(nodes rows: [JSONObject], links linkRows: [JSONObject]) -> JSONObject {
    var byId: [Int: JSONObject] = [:]
    for r in rows { if let id = r["id"] as? Int { byId[id] = r } }
    func label(_ id: Int?) -> String { id.flatMap { byId[$0]?["label"] as? String } ?? "" }
    func props(_ id: Int?) -> JSONObject { id.flatMap { byId[$0]?["p"] as? JSONObject } ?? [:] }
    func setProp(_ id: Int, _ key: String, _ value: Any) {
      var r = byId[id] ?? [:]
      var p = r["p"] as? JSONObject ?? [:]
      p[key] = value
      r["p"] = p
      byId[id] = r
    }
    let links = linkRows.map { l in (s: l["s"] as? Int ?? -1, t: l["t"] as? Int ?? -1, type: l["type"] as? String ?? "", p: l["p"]) }

    // A LoincCode without a name borrows the most common name of the observations coded by it.
    var names: [Int: [(name: String, count: Int)]] = [:]  // in first-seen order, as Python's Counter
    for l in links where l.type == "CODED_BY" && label(l.s) == "Observation" {
      let p = props(l.s)
      guard let n = str(p, "loincDisplay") ?? str(p, "display") else { continue }
      if let i = names[l.t]?.firstIndex(where: { $0.name == n }) { names[l.t]![i].count += 1 } else { names[l.t, default: []].append((n, 1)) }
    }
    for r in rows where r["label"] as? String == "LoincCode" {
      guard let id = r["id"] as? Int, str(props(id), "display") == nil, let counts = names[id] else { continue }
      // most_common(1): the highest count, the first seen on a tie
      var best = counts[0]
      for c in counts.dropFirst() where c.count > best.count { best = c }
      setProp(id, "display", best.name)
    }
    // ... and an observation without a name takes its code's.
    for l in links where l.type == "CODED_BY" && label(l.s) == "Observation" && label(l.t) == "LoincCode" {
      let o = props(l.s), c = props(l.t)
      let own = str(o, "display") ?? str(o, "loincDisplay")
      let codeName = c["display"] as? String
      if own == nil || own == (o["code"] as? String), let codeName, codeName != (c["code"] as? String) {
        setProp(l.s, "display", codeName)
      }
    }

    let markers = Set(links.filter { $0.type == "MARKER_OF" }.map(\.s) + links.filter { $0.type == "USES" }.map(\.t))
    var latest: [Int: Int] = [:]  // LoincCode id -> newest lab Observation id
    for l in links where l.type == "CODED_BY" && markers.contains(l.t) {
      let p = props(l.s)
      guard label(l.s) == "Observation", p["sourceKind"] as? String != "device-weekly-mean",
        str(p, "duplicateOf") == nil else { continue }
      let date = p["effectiveDate"] as? String ?? ""
      if let best = latest[l.t], (props(best)["effectiveDate"] as? String ?? "") >= date { continue }
      latest[l.t] = l.s
    }
    let current = Set(latest.values)
    var reportLab: [Int: String] = [:]
    for l in links where l.type == "HAS_RESULT" { reportLab[l.t] = props(l.s)["performer"] as? String }
    var omopCode: [Int: JSONObject] = [:]
    for l in links where l.type == "CODED_BY" && label(l.s) == "OMOPMeasurement" { omopCode[l.s] = props(l.t) }
    var sex: String?
    for r in rows where r["label"] as? String == "OMOPPerson" {
      switch props(r["id"] as? Int)["genderConceptId"] as? Int {
      case 8507: sex = "male"
      case 8532: sex = "female"
      default: break
      }
    }

    // An answer can explain a value (creatine for creatinine, hard exercise before a sample):
    // the question lists the choices that do (anamnesis ITEMS "explains").
    var itemOf: [Int: JSONObject] = [:]
    for l in links where l.type == "ANSWERS" && label(l.t) == "QuestionnaireItem" { itemOf[l.s] = props(l.t) }

    var nodes: [JSONObject] = []
    for r in rows {
      guard let id = r["id"] as? Int else { continue }
      let lab = r["label"] as? String ?? ""
      let p = props(id)
      let (group, name, lines) = describe(lab, p)
      var node: JSONObject = ["id": id, "g": group, "n": name, "d": lines.filter { !$0.isEmpty }]
      if lab == "OMOPMeasurement" {
        node["dt"] = p["measurementDate"] as? String ?? ""
        node["val"] = lines.first ?? ""
        if let code = omopCode[id], let d = code["display"] as? String, d != code["code"] as? String { node["n"] = d }
      }
      if lab == "Observation", isNumber(p["valueQuantity"]) {
        node["v"] = p["valueQuantity"]
        node["u"] = p["unit"] as? String ?? ""
        if group == "Lab value" {
          node["lab"] = str(p, "performer") ?? reportLab[id] ?? ""
          if isNumber(p["referenceLow"]) { node["rl"] = p["referenceLow"] }
          if isNumber(p["referenceHigh"]) { node["rh"] = p["referenceHigh"] }
        }
      }
      if lab == "HealthRisk" { node["rid"] = p["id"] ?? NSNull() }
      if lab == "Answer" {
        node["lk"] = str(p, "linkId") ?? ""
        node["ctx"] = str(p, "context") ?? ""
        node["au"] = str(p, "authored") ?? ""
        let codes = Set(p["codes"] as? [String] ?? []), explains = Set(itemOf[id]?["explains"] as? [String] ?? [])
        if !codes.isDisjoint(with: explains) { node["ex"] = 1 }
      }
      if lab == "Study" {
        node["sid"] = p["id"] ?? NSNull()
        node["year"] = p["year"] ?? NSNull()
        node["topics"] = p["topics"] ?? [String]()
        node["url"] = p["url"] ?? NSNull()
        node["pubmed"] = p["pubmedUrl"] ?? NSNull()
        if let s = str(p, "publicationStatus") { node["ps"] = s }
        if let v = str(p, "validity") { node["gv"] = v }
      }
      if lab == "ReferenceRange" {
        var rr: JSONObject = [:]
        for (k, f) in [("gl", "guidelineLow"), ("gh", "guidelineHigh"), ("ol", "optimalLow"), ("oh", "optimalHigh"),
                       ("u", "ucum"), ("sex", "sex"), ("src", "sourceLabel"), ("from", "validFrom"),
                       ("until", "validUntil"), ("y", "sourceYear"), ("by", "supersededBy")]
        where p[f] != nil && !(p[f] is NSNull) { rr[k] = p[f] }
        node["r"] = rr
      }
      if markers.contains(id) { node["mk"] = 1 }
      if current.contains(id) { node["cur"] = 1 }
      if lab == "Observation" {
        node["dt"] = str(p, "effectiveDate") ?? str(p, "effectiveStart") ?? ""
        node["val"] = lines.first ?? ""
        if str(p, "duplicateOf") != nil { node["dup"] = 1 }
        if group == "Lab value", let v = double(p["valueQuantity"]) {
          let lo = double(p["referenceLow"]), hi = double(p["referenceHigh"])
          if (lo.map { v < $0 } ?? false) || (hi.map { v > $0 } ?? false) {
            node["out"] = 1
            var d = node["d"] as? [String] ?? []
            d.insert("Outside the lab's range", at: min(1, d.count))
            node["d"] = d
          }
        }
      }
      nodes.append(node)
    }
    let outLinks: [JSONObject] = links.map { l in
      var o: JSONObject = ["source": l.s, "target": l.t, "t": l.type]
      if let p = l.p as? JSONObject, !p.isEmpty { o["p"] = p }
      return o
    }
    return ["nodes": nodes, "links": outLinks, "sex": sex ?? NSNull()]
  }
}

extension HealthStore {
  /// The page data of the 3D view: the graph, the person, the anamnesis protocols and the anamnesis plan
  /// (findings and the tests to ask the doctor for).
  public func graph3DData(today: String) throws -> JSONObject {
    let nodes = try objects("MATCH (n) RETURN id(n) AS id, labels(n)[0] AS label, properties(n) AS p")
    let links = try objects("""
      MATCH (a)-[r]->(b) RETURN id(a) AS s, id(b) AS t, type(r) AS type,
             CASE WHEN type(r) IN ['RAISES_RISK_OF', 'DISAGREES_WITH', 'AFTER_CUTOFF_OF'] THEN properties(r) END AS p
      """)
    var data = Graph3D.build(nodes: nodes, links: links)
    let person = try objects("MATCH (p:Patient) RETURN p.birthYear AS y, p.gender AS g").first ?? [:]
    let birth = person["y"] as? Int, gender = person["g"] as? String
    let year = Int(today.prefix(4)) ?? Calendar.current.component(.year, from: Date())
    data["birthYear"] = birth ?? NSNull()
    data["age"] = birth.map { year - $0 } ?? NSNull()
    data["gender"] = gender ?? NSNull()
    data["region"] = "moderate"
    if data["sex"] is NSNull { data["sex"] = gender ?? NSNull() }
    data["protocols"] = try protocolPlan(today: today, birthYear: birth, sex: gender)
    data["anamnesis"] = try anamnesisPlan(today: today)
    data["today"] = today
    return data
  }

  /// The page itself: the template with the data in place of `/*DATA*/null`.
  public func graph3DPage(template: String, today: String) throws -> String {
    let json = try JSONSerialization.data(withJSONObject: try graph3DData(today: today), options: [])
    return template.replacingOccurrences(of: "/*DATA*/null", with: String(decoding: json, as: UTF8.self))
  }

  /// `protocols.plan()` without the values: the protocols with every answer the person gave before
  /// (and the age band from the year of birth) prefilled, scored, the ones answered this year last.
  public func protocolPlan(today: String, birthYear: Int?, sex: String?) throws -> JSONObject {
    var answers: [String: JSONObject] = [:]
    for a in try objects(Cypher.protocolLatestAnswers) { if let id = a["linkId"] as? String { answers[id] = a } }
    var done: [String: JSONObject] = [:]
    for r in try objects(Cypher.protocolResponses) { if let id = r["protocol"] as? String { done[id] = r } }
    let day = { (a: JSONObject) in String((a["authored"] as? String ?? "").prefix(10)) }
    func codes(_ link: String) -> [String] { answers[link]?["codes"] as? [String] ?? [] }
    func said(_ link: String) -> JSONObject? {
      guard let a = answers[link] else { return nil }
      let labels = (a["labels"] as? [String]).flatMap { $0.isEmpty ? nil : $0 } ?? codes(link)
      return ["text": "your answer on \(day(a)): \(labels.joined(separator: ", "))", "date": day(a)]
    }
    func out(_ code: String, _ src: JSONObject?) -> JSONObject {
      ["code": code, "text": src?["text"] ?? NSNull(), "observation": NSNull(), "date": src?["date"] ?? NSNull()]
    }
    let year = Int(today.prefix(4)) ?? 0
    // The prefills that need no value: the answers the person gave and their year of birth.
    func prefill(_ name: String, _ item: JSONObject) -> JSONObject? {
      let options = Set(Protocols.options(item).compactMap { $0.string("code") })
      if name == "age", let b = birthYear {
        let age = year - b
        let code = age < 45 ? "<45" : age < 55 ? "45-54" : age < 65 ? "55-64" : "65+"
        return options.contains(code) ? out(code, ["text": "year of birth \(b)", "date": NSNull()]) : nil
      }
      if name.hasPrefix("answer:") {
        let link = String(name.dropFirst(7))
        if let c = codes(link).first, options.contains(c) { return out(c, said(link)) }
        return nil
      }
      if name.hasPrefix("diet:") {
        let d = codes("diet-pattern").first, food = String(name.dropFirst(5))
        if d == "vegan" || (d == "vegetarian" && (food == "meat" || food == "fish")) { return out("never", said("diet-pattern")) }
        return nil
      }
      switch name {
      case "bp_drug":
        if let c = codes("blood-pressure").first, ["treated", "no", "untreated"].contains(c) {
          return out(c == "treated" ? "yes" : "no", said("blood-pressure"))
        }
      case "lipid_drug":
        if let c = codes("lipid-medication").first {
          return out(["statin", "combination"].contains(c) ? "yes" : "no", said("lipid-medication"))
        }
      case "tobacco":
        switch codes("smoking").first {
        case "never": return out("never", said("smoking"))
        case "current": return out("current", said("smoking"))
        case "former":
          if let q = codes("tobacco-quit").first, let c = ["<1y": "quit-recent", "1-5y": "quit-1y", "5y+": "quit-5y"][q] {
            return out(c, said("tobacco-quit"))
          }
        default: break
        }
      case "home_smoke":
        if let c = codes("tobacco-home").first { return out(c, said("tobacco-home")) }
      case "family_diabetes":
        if codes("family-diabetes").first == "yes" { return out("close", said("family-diabetes")) }
      case "alcohol_none":
        if codes("alcohol").first == "none" { return out("never", said("alcohol")) }
      case "wine_week":
        if let c = codes("alcohol").first, ["none", "1-7"].contains(c) { return out("no", said("alcohol")) }
      default: break
      }
      return nil
    }

    let prefillText = Protocols.data.object("prefillText") ?? [:]
    let evidence = Protocols.data.object("evidence") ?? [:]
    let todayDate = ISO8601DateFormatter().date(from: today + "T00:00:00Z") ?? Date()
    var result: [(JSONObject, Double, Int)] = []
    for (order, p) in Protocols.definitions.enumerated() {
      var given: [String: [String]] = [:]
      var items: [JSONObject] = []
      for it in Protocols.items(p) {
        let link = it.string("linkId") ?? ""
        let a = answers[link]
        var pre: JSONObject?
        if it.string("type") == "month" {
          if let a, let t = a["text"] as? String, !t.isEmpty {
            pre = ["code": NSNull(), "value": t, "text": "your answer on \(day(a))", "observation": NSNull(), "date": day(a)]
          }
        } else if let name = it.string("prefill") {
          pre = prefill(name, it)
        }
        if pre == nil, let a, let c = (a["codes"] as? [String])?.first, Protocols.option(it, c) != nil {
          pre = ["code": c, "text": "your answer on \(day(a))", "observation": NSNull(), "date": day(a)]
        }
        if let c = pre?["code"] as? String { given[link] = [c] }
        var item: JSONObject = [:]
        for k in ["linkId", "text", "loinc", "snomed", "type", "metric", "enableWhen", "skipIf", "multiple"] {
          item[k] = it[k] ?? NSNull()
        }
        item["options"] = it["options"] ?? [Any]()
        item["prefilled"] = pre ?? NSNull()
        item["prefillFrom"] = it.string("prefill").flatMap { prefillText[$0] } ?? NSNull()
        items.append(item)
      }
      for i in items.indices { items[i]["enabled"] = Protocols.enabled(items[i], given) }
      let prefilled = items.filter { !($0["prefilled"] is NSNull) }.count
      var relevance = Double(prefilled) / Double(max(1, items.count))
      if p.string("id") == "tobacco" && answers["smoking"] == nil { relevance += 1 }
      let last = done[p.string("id") ?? ""]
      if let last, let authored = last["authored"] as? String,
        let when = ISO8601DateFormatter().date(from: String(authored.prefix(10)) + "T00:00:00Z"),
        todayDate.timeIntervalSince(when) <= 365 * 86_400
      {
        relevance -= 10
      }
      var entry: JSONObject = [:]
      for k in ["id", "name", "title", "kind", "year", "source", "pmid", "doi", "url", "licence", "loinc", "snomed",
                "scoreSnomed", "risks", "why", "method", "bands", "cutOff", "flagFrom", "flagBelow", "bandSnomed"] {
        entry[k] = p[k] ?? NSNull()
      }
      entry["critical"] = p["critical"] ?? [String]()
      entry["evidence"] = ((p["evidence"] as? [String]) ?? []).compactMap { id -> JSONObject? in
        guard var e = evidence[id] as? JSONObject else { return nil }
        e["id"] = id
        return e
      }
      entry["forYou"] = [String]()
      entry["relevance"] = (relevance * 100).rounded() / 100
      entry["items"] = items
      entry["prefilled"] = prefilled
      entry["score"] = Protocols.score(p, given, sex: sex) ?? NSNull()
      entry["lastAnswered"] = last ?? NSNull()
      entry["labs"] = NSNull()
      result.append((entry, relevance, order))
    }
    let sorted = result.sorted { $0.1 != $1.1 ? $0.1 > $1.1 : $0.2 < $1.2 }.map(\.0)
    var snomed: JSONObject = [:]
    for s in Protocols.data.objects("snomed") {
      if let c = s.string("code") { snomed[c] = ["display": s["display"] ?? "", "tag": s["tag"] ?? ""] }
    }
    return ["asOf": today, "sex": sex ?? NSNull(), "birthYear": birthYear ?? NSNull(),
            "category": Protocols.data["category"] ?? [:], "protocols": sorted, "treatedLipids": [Any](),
            "snomed": snomed]
  }
}
