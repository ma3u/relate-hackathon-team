import Foundation
import Relate

/// A doctor's letter the person prepares for a visit, from their own health graph: for the GP
/// (an overview of everything) or for a specialist (one health risk, its markers, the risks it
/// raises and is raised by, and the answers that bear on it).
///
/// What it holds is read, never judged: the latest lab tests exactly as printed (value, unit, the
/// lab's printed range, report, lab and the printed line), every marker's dated values compared
/// only with a guideline range in the same unit that applied on the value's date (and the range's
/// source named), the Apple Watch weekly means (the recent 12 weeks against the year before),
/// sport and activity, the latest anamnesis answer per question in the person's own words, and
/// plain questions for the doctor. A value seen in two reports counts once. The reads are in
/// `health_graph/letter.py`, generated into Cypher.swift.
///
/// Render it with `html(language:)` (a printable A4 page, inline CSS, nothing loaded from
/// anywhere) or `markdown(language:)`, in German or English.
public struct DoctorLetter {
  public enum Variant: Hashable, Sendable {
    /// The GP (Hausarzt): an overview of everything.
    case gp
    /// A specialist (Facharzt): one HealthRisk by id, e.g. "cardiovascular".
    case specialist(String)

    public var riskId: String? {
      if case .specialist(let id) = self { return id }
      return nil
    }
  }

  public enum Language: String, Sendable, CaseIterable {
    case de, en

    /// German when the locale's language is German, else English.
    public init(locale: Locale) {
      let code = locale.language.languageCode?.identifier ?? locale.identifier
      self = code.lowercased().hasPrefix("de") ? .de : .en
    }
  }

  /// A guideline range from the knowledge layer, as it applied on a value's date.
  public struct Range: Sendable, Equatable {
    public let low: Double?
    public let high: Double?
    public let unit: String
    public let sex: String
    public let validFrom: String?
    public let validUntil: String?
    public let source: String
    public let supersededBy: String?
  }

  public enum Flag: String, Sendable { case low, high, ok }

  /// One lab value as printed on its report.
  public struct LabValue: Sendable {
    public let id: String?
    public let code: String?
    public let display: String
    public let value: String
    public let number: Double?
    public let comparator: String?
    public let unit: String?
    public let date: String
    public let labLow: Double?
    public let labHigh: Double?
    public let labText: String?
    public let sourceLine: String?
    public let report: String?
    public let reportTitle: String?
    public let performer: String?
    /// The guideline range in this unit valid on this date, if the knowledge layer has one.
    public var guideline: Range?
    /// Against the guideline range, else against the lab's printed range; nil without either.
    public var flag: Flag?
    /// True when `flag` was judged against the lab's printed range.
    public var flagByLab = false

    /// One marker in one unit: a trend compares only values of the same unit.
    var key: String { "\(code ?? display)|\((unit ?? "").lowercased())" }
  }

  /// One paper report and the values printed on it.
  public struct Report: Sendable {
    public let id: String?
    public let title: String
    public let date: String
    public let performer: String?
    public let values: [LabValue]
  }

  public enum Direction: String, Sendable { case rising, falling, stable, single }

  /// Every dated value of one marker in one unit.
  public struct Trend: Sendable {
    public let code: String?
    public let display: String
    public let unit: String?
    public let values: [LabValue]

    public var first: LabValue { values[0] }
    public var last: LabValue { values[values.count - 1] }
    /// Relative change from the first to the last value, when both are numbers.
    public var change: Double? {
      guard values.count > 1, let a = first.number, let b = last.number, a != 0 else { return nil }
      return (b - a) / abs(a)
    }
    public var direction: Direction {
      guard values.count > 1 else { return .single }
      guard let c = change else { return .stable }
      return c > 0.05 ? .rising : c < -0.05 ? .falling : .stable
    }
  }

  /// One Apple Watch metric: the mean of the recent 12 weeks against the mean of the year before.
  public struct WeeklyTrend: Sendable {
    public let code: String
    public let display: String
    public let unit: String
    public let recentMean: Double
    public let recentWeeks: Int
    public let priorMean: Double?
    public let priorWeeks: Int
    public let lastDate: String
  }

  /// The latest answer to one question, as the person gave it.
  public struct Answer: Sendable {
    public let linkId: String
    public let question: String
    public let labels: [String]
    public let text: String?
    public let context: String?
    public let authored: String
    public let protocolId: String?
    public let protocolName: String?
    public let riskFactor: Bool
  }

  /// A questionnaire's newest score.
  public struct Score: Sendable {
    public let protocolId: String
    public let name: String
    public let score: String?
    public let band: String?
    public let authored: String
  }

  /// How one risk raises another (RAISES_RISK_OF), with the source's summary.
  public struct RiskLink: Sendable {
    public let fromId: String, fromName: String, toId: String, toName: String
    public let summary: String?
  }

  public enum Question: Sendable {
    /// The newest value of a marker is outside the range; with its trend when there is one.
    case outOfRange(LabValue, Trend?)
    /// A marker rose by more than 10 % from its first to its last value.
    case rising(Trend)
    /// A test the anamnesis plan suggests asking for.
    case test(String)
    /// Anamnesis questions the plan still asks.
    case unanswered([String])
  }

  public let variant: Variant
  /// The day the letter was prepared (YYYY-MM-DD).
  public let date: String
  public let birthYear: Int?
  public let sex: String?
  /// The HealthRisk in focus (specialist), with its name as the graph has it.
  public let riskName: String?
  public let markers: Set<String>
  /// The newest lab report(s): for the GP the newest report date; for a specialist the newest value
  /// of each of the risk's markers, grouped by report.
  public let latest: [Report]
  public let trends: [Trend]
  public let vitals: [WeeklyTrend]
  public let activity: [WeeklyTrend]
  /// The 12-week window the weekly means are compared in (from, to), when there are any.
  public let window: (from: String, to: String)?
  /// Exercise tests and lung function reports, when the graph has any.
  public let exerciseReports: [Report]
  public let answers: [Answer]
  public let scores: [Score]
  public let links: [RiskLink]
  public let questions: [Question]
  /// How many lab reports and values the letter rests on.
  public let reportCount: Int
  public let valueCount: Int

  /// The person's own answer about exercise (the anamnesis `exercise` question), if given.
  public var exerciseAnswer: Answer? { answers.first { $0.linkId == "exercise" } }

  // MARK: Reading the graph

  static let vitalCodes = ["40443-4", "80404-7", "59408-5", "9279-1", "29463-7", "41982-0", "93832-4"]
  static let activityCodes = ["55411-3", "41950-7", "94122-9", "41981-2"]
  /// Exercise blood pressure, spirometry (FEV1, FVC, FEV1/FVC): a report holding one is an exercise or lung test.
  static let exerciseTestCodes: Set<String> = ["87739-9", "20150-9", "19870-5", "19926-5"]
  static let exerciseTitleWords = [
    "ergometr", "belastung", "spiroergo", "spirometr", "lungenfunktion", "leistungsdiagnost", "exercise",
    "stress test", "cpet", "spirometry", "lung function", "cardiopulmonary",
  ]

  static func double(_ any: Any?) -> Double? {
    guard let n = any as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
    return n.doubleValue
  }

  static func plain(_ any: Any?) -> String {
    switch any {
    case let s as String: return s
    case let n as NSNumber where CFGetTypeID(n) != CFBooleanGetTypeID():
      return CFNumberIsFloatType(n) ? number(n.doubleValue) : String(n.int64Value)
    case nil, is NSNull: return ""
    default: return "\(any!)"
    }
  }

  /// A number without a trailing ".0" (1240, not 1240.0), with a decimal point.
  static func number(_ d: Double) -> String {
    if d.isFinite, d == d.rounded(), abs(d) < 1e15 { return String(Int64(d)) }
    return String(d)
  }

  /// The guideline range for a value: the same unit (case aside), the person's sex or any, valid on the date.
  static func range(_ ranges: [Range], unit: String?, date: String, sex: String?) -> Range? {
    guard let unit = unit?.lowercased(), !unit.isEmpty else { return nil }
    let day = String(date.prefix(10))
    let valid = ranges.filter { r in
      r.unit.lowercased() == unit && (r.validFrom ?? "0000") <= day
        && (r.validUntil.map { day < $0 } ?? true)
        && (r.sex == "any" || r.sex == (sex ?? "any"))
    }
    return valid.first { $0.sex == sex } ?? valid.first
  }

  static func flag(_ value: Double, low: Double?, high: Double?) -> Flag {
    if let high, value > high { return .high }
    if let low, value < low { return .low }
    return .ok
  }

  static func addDays(_ day: String, _ n: Int) -> String {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(identifier: "UTC")
    f.dateFormat = "yyyy-MM-dd"
    guard let d = f.date(from: String(day.prefix(10))) else { return day }
    return f.string(from: d.addingTimeInterval(Double(n) * 86_400))
  }

  static func mean(_ xs: [Double]) -> Double? { xs.isEmpty ? nil : xs.reduce(0, +) / Double(xs.count) }

  /// The risks an anamnesis or protocol answer bears on.
  static func risks(linkId: String, protocolId: String?) -> Set<String> {
    if let protocolId, let p = Protocols.definition(protocolId) {
      return Set((p["risks"] as? [String] ?? []) + (p["flagRisks"] as? [String] ?? []))
    }
    return Set(Anamnesis.item(linkId)?["risks"] as? [String] ?? [])
  }
}

extension HealthStore {
  /// The health risks with how many values the graph has on their markers (lab values counted once,
  /// Apple Watch weeks included): what a specialist's letter can be about.
  public func letterRisks() throws -> [(id: String, name: String, values: Int)] {
    var perCode: [String: Int] = [:]
    for v in try objects(Cypher.letterLabValues) { if let c = v.string("code") { perCode[c, default: 0] += 1 } }
    for v in try objects(Cypher.letterDeviceValues) { if let c = v.string("code") { perCode[c, default: 0] += 1 } }
    return try objects(Cypher.letterRisks).compactMap { r in
      guard let id = r.string("id") else { return nil }
      let n = (r["codes"] as? [String] ?? []).reduce(0) { $0 + (perCode[$1] ?? 0) }
      return (id, r.string("name") ?? id, n)
    }
  }

  /// Builds the letter from this store. `today` (YYYY-MM-DD) defaults to the current day.
  public func doctorLetter(_ variant: DoctorLetter.Variant = .gp, today: String? = nil) throws -> DoctorLetter {
    typealias L = DoctorLetter
    let today = today ?? ISO8601DateFormatter.string(from: Date(), timeZone: .current, formatOptions: [.withFullDate])
    let person = try objects(Cypher.letterPatient).first ?? [:]
    let birthYear = (person["birthYear"] as? NSNumber)?.intValue
    let sex = person.string("sex")

    // The risk in focus and its markers.
    var riskName: String?
    var markers: Set<String> = []
    if let id = variant.riskId {
      guard let risk = try objects(Cypher.letterRisks).first(where: { $0.string("id") == id }) else {
        throw HealthGraphError.invalid("unknown health risk \(id)")
      }
      riskName = risk.string("name") ?? id
      markers = Set(risk["codes"] as? [String] ?? [])
    }
    let focus = variant.riskId
    func relevant(_ code: String?) -> Bool { focus == nil || code.map(markers.contains) == true }

    // Lab values, each with the guideline range valid on its date in its unit.
    let rows = try objects(Cypher.letterLabValues)
    let codes = Array(Set(rows.compactMap { $0.string("code") } + L.vitalCodes + L.activityCodes)).sorted()
    var ranges: [String: [L.Range]] = [:]
    for r in try objects(Cypher.letterRanges, ["codes": .list(codes.map(CypherValue.string))]) {
      guard let code = r.string("code"), let unit = r.string("ucum") else { continue }
      ranges[code, default: []].append(L.Range(
        low: L.double(r["low"]), high: L.double(r["high"]), unit: unit, sex: r.string("sex") ?? "any",
        validFrom: r.text("validFrom"), validUntil: r.text("validUntil"), source: r.string("source") ?? "",
        supersededBy: r.text("supersededBy")))
    }
    var values: [L.LabValue] = rows.compactMap { r in
      guard let date = r.text("date") else { return nil }
      let code = r.text("code")
      var v = L.LabValue(
        id: r.text("id"), code: code, display: r.text("display") ?? code ?? "?", value: L.plain(r["value"]),
        number: L.double(r["value"]), comparator: r.text("comparator"), unit: r.text("unit"),
        date: String(date.prefix(10)), labLow: L.double(r["labLow"]), labHigh: L.double(r["labHigh"]),
        labText: r.text("labText"), sourceLine: r.text("sourceLine"), report: r.text("report"),
        reportTitle: r.text("title"), performer: r.text("performer"))
      v.guideline = code.flatMap { ranges[$0] }.flatMap { L.range($0, unit: v.unit, date: v.date, sex: sex) }
      if let n = v.number {
        if let g = v.guideline, g.low != nil || g.high != nil {
          v.flag = L.flag(n, low: g.low, high: g.high)
        } else if v.labLow != nil || v.labHigh != nil {
          v.flag = L.flag(n, low: v.labLow, high: v.labHigh)
          v.flagByLab = true
        }
      }
      return v
    }
    values.sort { ($0.date, $0.display) < ($1.date, $1.display) }

    // Reports: lab reports and exercise or lung function tests.
    var byReport: [String: [L.LabValue]] = [:]
    for v in values { byReport[v.report ?? "no-report|\(v.date)", default: []].append(v) }
    let reports: [L.Report] = byReport.map { id, vs in
      L.Report(id: vs[0].report, title: vs[0].reportTitle ?? "", date: vs.map(\.date).max() ?? "",
               performer: vs[0].performer, values: vs)
    }.sorted { ($0.date, $0.title) > ($1.date, $1.title) }
    func isExercise(_ r: L.Report) -> Bool {
      let title = r.title.lowercased()
      return L.exerciseTitleWords.contains { title.contains($0) }
        || r.values.contains { $0.code.map(L.exerciseTestCodes.contains) == true }
    }
    let labReports = reports.filter { !isExercise($0) }
    var exerciseReports = reports.filter(isExercise)
    if let focus, !["fitness", "cardiovascular"].contains(focus) { exerciseReports = [] }

    var latest: [L.Report] = []
    if focus == nil {
      if let newest = labReports.first?.date { latest = labReports.filter { $0.date == newest } }
    } else {
      // The newest value of each marker, grouped by the report it was printed on.
      var newest: [String: L.LabValue] = [:]
      for r in labReports { for v in r.values where relevant(v.code) && newest[v.key] == nil { newest[v.key] = v } }
      let keep = Set(newest.values.compactMap(\.id))
      latest = labReports.compactMap { r in
        let vs = r.values.filter { $0.id.map(keep.contains) == true }
        return vs.isEmpty ? nil : L.Report(id: r.id, title: r.title, date: r.date, performer: r.performer, values: vs)
      }
    }

    // Trends: every marker in every unit, in date order.
    var grouped: [String: [L.LabValue]] = [:]
    for r in labReports { for v in r.values where relevant(v.code) { grouped[v.key, default: []].append(v) } }
    // Markers whose newest value is outside its range first, then by name.
    func rank(_ t: L.Trend) -> Int { t.last.flag == .high || t.last.flag == .low ? 0 : 1 }
    let trends: [L.Trend] = grouped.values.map { vs -> L.Trend in
      let sorted = vs.sorted { $0.date < $1.date }
      return L.Trend(code: sorted[0].code, display: sorted[sorted.count - 1].display, unit: sorted[0].unit, values: sorted)
    }.sorted { a, b in rank(a) != rank(b) ? rank(a) < rank(b) : a.display < b.display }

    // Apple Watch weekly means: the recent 12 weeks against the year before.
    let device = try objects(Cypher.letterDeviceValues)
    let newestWeek = device.compactMap { $0.text("date").map { String($0.prefix(10)) } }.max()
    var window: (from: String, to: String)?
    var weekly: [String: L.WeeklyTrend] = [:]
    if let newestWeek {
      let anchor = min(newestWeek, today)
      let recentFrom = L.addDays(anchor, -84), priorFrom = L.addDays(anchor, -84 - 365)
      window = (L.addDays(recentFrom, 1), anchor)
      var series: [String: [(String, Double, String, String)]] = [:]
      for d in device {
        guard let code = d.string("code"), let date = d.text("date"), let v = L.double(d["value"]) else { continue }
        series[code, default: []].append((String(date.prefix(10)), v, d.string("unit") ?? "", d.string("display") ?? code))
      }
      for (code, points) in series {
        let recent = points.filter { $0.0 > recentFrom && $0.0 <= anchor }.map(\.1)
        let prior = points.filter { $0.0 > priorFrom && $0.0 <= recentFrom }.map(\.1)
        guard let r = L.mean(recent) else { continue }
        weekly[code] = L.WeeklyTrend(
          code: code, display: points.last?.3 ?? code, unit: points.last?.2 ?? "", recentMean: r,
          recentWeeks: recent.count, priorMean: L.mean(prior), priorWeeks: prior.count,
          lastDate: points.map(\.0).max() ?? anchor)
      }
    }
    let vitals = L.vitalCodes.compactMap { weekly[$0] }.filter { relevant($0.code) }
    let activity = L.activityCodes.compactMap { weekly[$0] }.filter { relevant($0.code) }

    // Anamnesis: the latest answer per question, and the questionnaires' newest scores.
    var answers: [L.Answer] = try objects(Cypher.letterAnswers).compactMap { a in
      guard let link = a.string("linkId") else { return nil }
      let pid = a.text("protocol")
      return L.Answer(
        linkId: link, question: a.text("question") ?? Anamnesis.item(link)?.string("text") ?? link,
        labels: a["labels"] as? [String] ?? [], text: a.text("text"), context: a.text("context"),
        authored: String((a.string("authored") ?? "").prefix(10)), protocolId: pid,
        protocolName: pid.flatMap { Protocols.definition($0)?.string("name") },
        riskFactor: (a["riskFactor"] as? Bool) ?? false)
    }
    var scores: [L.Score] = try objects(Cypher.protocolResponses).compactMap { r in
      guard let pid = r.string("protocol") else { return nil }
      return L.Score(protocolId: pid, name: Protocols.definition(pid)?.string("name") ?? pid,
                     score: r["score"].map(L.plain).flatMap(nonEmpty), band: r.text("band"),
                     authored: String((r.string("authored") ?? "").prefix(10)))
    }.sorted { $0.name < $1.name }
    if let focus {
      answers = answers.filter { L.risks(linkId: $0.linkId, protocolId: $0.protocolId).contains(focus) }
      scores = scores.filter { L.risks(linkId: "", protocolId: $0.protocolId).contains(focus) }
    }
    // Anamnesis answers first, then protocol by protocol, each newest first.
    answers.sort { a, b in
      let ka = a.protocolName ?? "", kb = b.protocolName ?? ""
      return ka != kb ? ka < kb : a.authored != b.authored ? a.authored > b.authored : a.linkId < b.linkId
    }

    // How the risk in focus raises others and is raised by them.
    var links: [L.RiskLink] = []
    if let focus {
      links = try objects(Cypher.letterRiskLinks, ["risk": .string(focus)]).map {
        L.RiskLink(fromId: $0.string("fromId") ?? "", fromName: $0.string("fromName") ?? "",
                   toId: $0.string("toId") ?? "", toName: $0.string("toName") ?? "", summary: $0.text("summary"))
      }
    }

    // Questions for the doctor, plainly: out-of-range values, rising trends, the plan's tests and open questions.
    var questions: [L.Question] = []
    for t in trends where t.last.flag == .high || t.last.flag == .low {
      questions.append(.outOfRange(t.last, t.values.count > 1 ? t : nil))
    }
    for t in trends where t.last.flag != .high && t.last.flag != .low && t.values.count > 1 {
      if let c = t.change, c > 0.10 { questions.append(.rising(t)) }
    }
    if let plan = try? anamnesisPlan(today: today) {
      var tests: [String] = []
      for f in plan["findings"] as? [JSONObject] ?? [] {
        let risks = Set(f["risks"] as? [String] ?? [])
        guard focus.map(risks.contains) ?? true else { continue }
        for t in f["tests"] as? [String] ?? [] where !tests.contains(t) { tests.append(t) }
      }
      questions += tests.map { .test($0) }
      let open = (plan["questions"] as? [JSONObject] ?? []).filter { q in
        focus.map { Set(q["risks"] as? [String] ?? []).contains($0) } ?? true
      }.compactMap { $0.string("text") }
      if !open.isEmpty { questions.append(.unanswered(Array(open.prefix(6)))) }
    }

    let counted = labReports.flatMap(\.values)
    return DoctorLetter(
      variant: variant, date: today, birthYear: birthYear, sex: sex, riskName: riskName, markers: markers,
      latest: latest, trends: trends, vitals: vitals, activity: activity, window: window,
      exerciseReports: exerciseReports, answers: answers, scores: scores, links: links,
      questions: Array(questions.prefix(10)),
      reportCount: Set(labReports.compactMap(\.id)).count, valueCount: counted.count)
  }
}

extension Anamnesis {
  /// The text of an anamnesis question by linkId, a dated one with "that day" for its date.
  public static func questionText(_ linkId: String) -> String? {
    item(linkId)?.string("text")?.replacingOccurrences(of: "{date}", with: "that day")
  }
}
