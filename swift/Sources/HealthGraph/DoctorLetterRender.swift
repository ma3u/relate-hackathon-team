import Foundation

/// The doctor's letter as text: one content model, rendered as a printable A4 HTML page or as
/// Markdown, in German or English. Numbers, units and printed lines are the graph's; only the
/// words around them are translated.
extension DoctorLetter {
  struct Cell {
    let text: String
    var strong = false
    init(_ text: String, strong: Bool = false) {
      self.text = text
      self.strong = strong
    }
  }

  enum Block {
    case paragraph(String, note: Bool)
    case heading(String)
    case table([String], [[Cell]])
    case list([String], ordered: Bool)
  }

  struct Section {
    let title: String
    var blocks: [Block]
  }

  struct Content {
    let title: String
    let subtitle: String
    let meta: [(String, String)]
    let sections: [Section]
    let footer: String
  }

  // MARK: Words

  struct Words {
    let language: Language
    func s(_ en: String, _ de: String) -> String { language == .de ? de : en }

    func date(_ iso: String) -> String {
      let d = String(iso.prefix(10))
      guard language == .de else { return d }
      let p = d.split(separator: "-")
      return p.count == 3 ? "\(p[2]).\(p[1]).\(p[0])" : d
    }

    func number(_ x: Double) -> String { decimal(DoctorLetter.number(x)) }
    func decimal(_ s: String) -> String { language == .de ? s.replacingOccurrences(of: ".", with: ",") : s }

    /// A weekly mean: whole numbers for steps and energy, one decimal otherwise.
    func mean(_ x: Double, unit: String) -> String {
      if abs(x) >= 100 { return decimal(String(Int((x).rounded()))) }
      return decimal(String(format: "%.1f", x))
    }

    func sex(_ s: String?) -> String {
      switch s {
      case "male": return self.s("male", "männlich")
      case "female": return self.s("female", "weiblich")
      case "other": return self.s("other", "divers")
      default: return self.s("not shared", "nicht angegeben")
      }
    }

    func risk(_ id: String, _ name: String) -> String {
      guard language == .de else { return name }
      return [
        "cardiovascular": "Herz-Kreislauf-Erkrankung", "diabetes": "Typ-2-Diabetes",
        "kidney": "Chronische Nierenerkrankung", "liver": "Leberfibrose",
        "fitness": "Geringe kardiorespiratorische Fitness", "bone": "Osteoporose",
      ][id] ?? name
    }

    func metric(_ code: String, _ display: String) -> String {
      let names: [String: (String, String)] = [
        "40443-4": ("Resting heart rate", "Ruhepuls"),
        "80404-7": ("Heart rate variability (SDNN)", "Herzfrequenzvariabilität (SDNN)"),
        "59408-5": ("Blood oxygen (SpO2)", "Sauerstoffsättigung (SpO2)"),
        "9279-1": ("Respiratory rate", "Atemfrequenz"),
        "29463-7": ("Body weight", "Körpergewicht"),
        "41982-0": ("Body fat", "Körperfettanteil"),
        "93832-4": ("Sleep", "Schlaf"),
        "55411-3": ("Exercise minutes", "Trainingsminuten"),
        "41950-7": ("Steps", "Schritte"),
        "94122-9": ("VO2 max (cardio fitness, Apple Watch estimate)", "VO2max (Cardio-Fitness, Schätzung der Apple Watch)"),
        "41981-2": ("Active energy", "Aktivitätsenergie"),
      ]
      guard let n = names[code] else { return display }
      return s(n.0, n.1)
    }

    func value(_ v: LabValue) -> String {
      let n = v.comparator.map { $0 + decimal(v.value) } ?? decimal(v.value)
      return v.unit.map { "\(n) \($0)" } ?? n
    }

    func arrow(_ v: LabValue) -> String {
      switch v.flag {
      case .high?: return " ↑"
      case .low?: return " ↓"
      default: return ""
      }
    }

    func bounds(_ low: Double?, _ high: Double?, unit: String?) -> String? {
      let u = unit.map { " \($0)" } ?? ""
      switch (low, high) {
      case let (l?, h?): return "\(number(l)) – \(number(h))\(u)"
      case let (l?, nil): return "≥ \(number(l))\(u)"
      case let (nil, h?): return "≤ \(number(h))\(u)"
      default: return nil
      }
    }

    /// The lab's printed range: its text when it printed one, else its numbers.
    func labRange(_ v: LabValue) -> String {
      v.labText ?? bounds(v.labLow, v.labHigh, unit: v.unit) ?? "–"
    }

    func guideline(_ v: LabValue) -> String {
      guard let g = v.guideline, let b = bounds(g.low, g.high, unit: g.unit) else { return "–" }
      var out = "\(b) (\(g.source)"
      if let until = g.validUntil {
        out += s(", superseded on \(date(until))", ", ersetzt am \(date(until))")
        if let by = g.supersededBy { out += s(" by \(by)", " durch \(by)") }
      }
      return out + ")"
    }

    func range(_ v: LabValue) -> String {
      if v.guideline != nil && !v.flagByLab { return guideline(v) }
      if v.labText == nil && v.labLow == nil && v.labHigh == nil { return s("no range", "kein Bereich") }
      return labRange(v) + s(" (the lab's printed range)", " (Referenzbereich des Labors)")
    }

    func direction(_ t: Trend) -> String {
      let pct = t.change.map { c -> String in
        let p = Int((c * 100).rounded())
        return " (\(p > 0 ? "+" : "")\(p) %)"
      } ?? ""
      switch t.direction {
      case .rising: return s("rising", "steigend") + pct
      case .falling: return s("falling", "fallend") + pct
      case .stable: return s("stable", "stabil") + pct
      case .single: return s("one value", "ein Wert")
      }
    }

    func source(_ r: Report) -> String {
      [r.title.isEmpty ? nil : r.title, r.performer, date(r.date)].compactMap { $0 }.joined(separator: ", ")
    }
  }

  // MARK: Content

  func content(_ language: Language) -> Content {
    let w = Words(language: language)
    let s = w.s
    let riskLabel = variant.riskId.map { w.risk($0, riskName ?? $0) }

    let title: String
    if let riskLabel {
      title = s("Doctor's letter for my specialist: \(riskLabel)", "Arztbrief für die Facharztpraxis: \(riskLabel)")
    } else {
      title = s("Doctor's letter for my GP", "Arztbrief für die Hausarztpraxis")
    }
    let subtitle = s(
      "Prepared by the patient with Klarbefund on \(w.date(date)). A summary of my own records, not a medical assessment.",
      "Vom Patienten mit Klarbefund erstellt am \(w.date(date)). Eine Zusammenstellung meiner eigenen Unterlagen, keine ärztliche Bewertung.")
    var meta: [(String, String)] = [
      (s("Year of birth", "Geburtsjahr"), birthYear.map(String.init) ?? s("not shared", "nicht angegeben")),
      (s("Sex", "Geschlecht"), w.sex(sex)),
      (s("Lab reports", "Laborbefunde"), "\(reportCount) (\(valueCount) \(s("values", "Werte")))"),
    ]
    if let newest = trends.map(\.last.date).max() { meta.append((s("Newest lab value", "Neuester Laborwert"), w.date(newest))) }

    var sections: [Section] = []

    // 1. Reason for the visit and topics
    var reason: [Block] = []
    if let riskLabel {
      reason.append(.paragraph(s(
        "I would like to discuss this risk: \(riskLabel). Below are its markers in my records, how they developed, and how it connects to other risks.",
        "Ich möchte über dieses Risiko sprechen: \(riskLabel). Unten stehen die zugehörigen Messwerte aus meinen Unterlagen, ihr Verlauf und wie es mit anderen Risiken zusammenhängt."),
        note: false))
    } else {
      reason.append(.paragraph(s(
        "A check-up: an overview of my lab values, their trends, my Apple Watch data, my activity and my anamnesis.",
        "Eine Übersicht: meine Laborwerte und ihr Verlauf, meine Apple-Watch-Daten, meine Aktivität und meine Anamnese."),
        note: false))
    }
    let outside = trends.filter { $0.last.flag == .high || $0.last.flag == .low }
    var topics = outside.map { t in
      t.last.flag == .high
        ? s("\(t.display) above the range (\(w.value(t.last)), \(w.date(t.last.date)))",
            "\(t.display) über dem Bereich (\(w.value(t.last)), \(w.date(t.last.date)))")
        : s("\(t.display) below the range (\(w.value(t.last)), \(w.date(t.last.date)))",
            "\(t.display) unter dem Bereich (\(w.value(t.last)), \(w.date(t.last.date)))")
    }
    for t in trends where !outside.contains(where: { $0.display == t.display }) && (t.change ?? 0) > 0.10 {
      topics.append(s("\(t.display) rising (\(w.direction(t)))", "\(t.display) steigend (\(w.direction(t)))"))
    }
    if !topics.isEmpty {
      reason.append(.paragraph(s("Topics from my records:", "Themen aus meinen Unterlagen:"), note: false))
      reason.append(.list(topics, ordered: false))
    }
    sections.append(Section(title: s("Reason for the visit", "Anlass des Besuchs"), blocks: reason))

    // 2. Latest lab tests
    var labs: [Block] = []
    if latest.isEmpty {
      labs.append(.paragraph(s("No lab report in my records.", "Kein Laborbefund in meinen Unterlagen."), note: true))
    }
    for r in latest {
      labs.append(.heading(w.source(r)))
      labs.append(.table(
        [s("Test", "Wert"), s("Result", "Ergebnis"), s("Lab's range", "Referenz Labor"),
         s("Guideline range valid on that date", "Leitlinienbereich an diesem Datum"), s("As printed", "Gedruckte Zeile")],
        r.values.map { v in
          [Cell(v.display), Cell(w.value(v) + w.arrow(v), strong: v.flag == .high || v.flag == .low),
           Cell(w.labRange(v)), Cell(w.guideline(v)), Cell(v.sourceLine ?? "–")]
        }))
    }
    if !latest.isEmpty {
      labs.append(.paragraph(s(
        "↑ above, ↓ below the guideline range valid on the value's date in the same unit, else the lab's printed range.",
        "↑ über, ↓ unter dem Leitlinienbereich, der am Datum des Werts in derselben Einheit galt, sonst dem Referenzbereich des Labors."),
        note: true))
    }
    sections.append(Section(title: s("Latest lab tests", "Aktuelle Laborwerte"), blocks: labs))

    // 3. Trends
    var trendBlocks: [Block] = []
    if trends.isEmpty {
      trendBlocks.append(.paragraph(s("No lab values in my records.", "Keine Laborwerte in meinen Unterlagen."), note: true))
    } else {
      trendBlocks.append(.table(
        [s("Marker", "Messwert"), s("Values by date", "Werte nach Datum"), s("Direction, first to last", "Richtung, erster zu letztem"),
         s("Compared with", "Verglichen mit")],
        trends.map { t in
          let series = t.values.map { "\(w.date($0.date)): \(w.value($0))\(w.arrow($0))" }.joined(separator: " · ")
          return [Cell(t.display), Cell(series, strong: t.last.flag == .high || t.last.flag == .low),
                  Cell(w.direction(t)), Cell(w.range(t.last))]
        }))
      trendBlocks.append(.paragraph(s(
        "Each value is compared only with a range in its own unit that applied on its date; values in another unit form their own row.",
        "Jeder Wert wird nur mit einem Bereich in seiner Einheit verglichen, der an seinem Datum galt; Werte in einer anderen Einheit stehen in einer eigenen Zeile."),
        note: true))
    }
    sections.append(Section(title: s("Trends", "Verläufe"), blocks: trendBlocks))

    // 4 and 5. Apple Watch vital trends, sport and activity
    func weeklyTable(_ rows: [WeeklyTrend]) -> Block {
      .table(
        [s("Measure", "Messgröße"), s("Recent 12 weeks", "Letzte 12 Wochen"), s("The year before", "Das Jahr davor"),
         s("Change", "Änderung")],
        rows.map { m in
          let recent = "\(w.mean(m.recentMean, unit: m.unit)) \(m.unit) (\(m.recentWeeks) \(s("weeks", "Wochen")))"
          let prior = m.priorMean.map { "\(w.mean($0, unit: m.unit)) \(m.unit) (\(m.priorWeeks) \(s("weeks", "Wochen")))" }
            ?? s("no weeks", "keine Wochen")
          var change = "–"
          if let p = m.priorMean {
            let d = m.recentMean - p
            change = "\(d >= 0 ? "+" : "−")\(w.mean(abs(d), unit: m.unit)) \(m.unit)"
          }
          return [Cell(w.metric(m.code, m.display)), Cell(recent), Cell(prior), Cell(change)]
        })
    }
    let windowText = window.map { s("Weekly means of the Apple Watch, \(w.date($0.from)) to \(w.date($0.to)), against the 12 months before.",
                                     "Wochenmittel der Apple Watch, \(w.date($0.from)) bis \(w.date($0.to)), verglichen mit den 12 Monaten davor.") }
    var vitalBlocks: [Block] = []
    if vitals.isEmpty {
      vitalBlocks.append(.paragraph(s("No Apple Watch vital data in my records.", "Keine Vitaldaten der Apple Watch in meinen Unterlagen."), note: true))
    } else {
      if let windowText { vitalBlocks.append(.paragraph(windowText, note: true)) }
      vitalBlocks.append(weeklyTable(vitals))
    }
    sections.append(Section(title: s("Apple Watch vital trends", "Vitalwerte der Apple Watch"), blocks: vitalBlocks))

    var sport: [Block] = []
    if !activity.isEmpty {
      if let windowText { sport.append(.paragraph(windowText, note: true)) }
      sport.append(weeklyTable(activity))
    }
    if let a = exerciseAnswer {
      let said = ([a.labels.joined(separator: ", ")] + [a.text.map { s("“\($0)”", "„\($0)“") }].compactMap { $0 }).filter { !$0.isEmpty }
      sport.append(.paragraph(s("My answer (\(w.date(a.authored))): ", "Meine Angabe (\(w.date(a.authored))): ")
        + a.question + " " + said.joined(separator: " "), note: false))
    }
    for r in exerciseReports {
      sport.append(.heading(w.source(r)))
      sport.append(.table(
        [s("Test", "Wert"), s("Result", "Ergebnis"), s("Lab's range", "Referenz"), s("As printed", "Gedruckte Zeile")],
        r.values.map { [Cell($0.display), Cell(w.value($0) + w.arrow($0)), Cell(w.labRange($0)), Cell($0.sourceLine ?? "–")] }))
    }
    if sport.isEmpty {
      sport.append(.paragraph(s("No activity data, exercise test or answer about exercise in my records.",
                                "Keine Aktivitätsdaten, Belastungstests oder Angaben zu Sport in meinen Unterlagen."), note: true))
    }
    sections.append(Section(title: s("Sport and activity", "Sport und Aktivität"), blocks: sport))

    // 6. Anamnesis
    var history: [Block] = []
    if answers.isEmpty {
      history.append(.paragraph(s("No anamnesis answers stored yet.", "Noch keine Anamnese-Angaben gespeichert."), note: true))
    } else {
      history.append(.table(
        [s("Question", "Frage"), s("My answer", "Meine Antwort"), s("In my own words", "In meinen Worten"), s("Answered", "Angegeben")],
        answers.map { a in
          var q = a.question
          if let p = a.protocolName { q = "\(p): \(q)" }
          if let c = a.context, !q.contains(c) { q += s(" (about \(w.date(c)))", " (zum \(w.date(c)))") }
          return [Cell(q), Cell(a.labels.joined(separator: ", "), strong: a.riskFactor), Cell(a.text ?? ""),
                  Cell(w.date(a.authored))]
        }))
    }
    if language == .de && !answers.isEmpty {
      history.append(.paragraph(
        "Fragen und Antwortoptionen der Anamnese stehen so da, wie Klarbefund sie gestellt hat (englisch); eigene Worte wie angegeben.",
        note: true))
    }
    if !scores.isEmpty {
      history.append(.table(
        [s("Questionnaire", "Fragebogen"), s("Score", "Punkte"), s("Band", "Einordnung"), s("Answered", "Angegeben")],
        scores.map { [Cell($0.name), Cell($0.score.map(w.decimal) ?? "–"), Cell($0.band ?? "–"), Cell(w.date($0.authored))] }))
    }
    sections.append(Section(title: s("Anamnesis", "Anamnese"), blocks: history))

    // Specialist: how the risk connects to others
    if variant.riskId != nil {
      var related: [Block] = []
      if links.isEmpty {
        related.append(.paragraph(s("The knowledge layer links no other risk to this one.",
                                    "Die Wissensebene verknüpft kein anderes Risiko mit diesem."), note: true))
      } else {
        related.append(.list(links.map { l in
          let head = "\(w.risk(l.fromId, l.fromName)) → \(w.risk(l.toId, l.toName))"
          return l.summary.map { "\(head): \($0)" } ?? head
        }, ordered: false))
        related.append(.paragraph(s(
          "From meta-analyses and guidelines: associations, not proof of cause.",
          "Aus Metaanalysen und Leitlinien (Zusammenfassungen im englischen Original): Zusammenhänge, kein Beweis einer Ursache."),
          note: true))
      }
      sections.append(Section(title: s("Related risks", "Zusammenhängende Risiken"), blocks: related))
    }

    // 7. Questions for the doctor
    let asks: [String] = questions.map { q in
      switch q {
      case .outOfRange(let v, let t):
        let side = v.flag == .high ? s("above", "über") : s("below", "unter")
        var text = s(
          "My \(v.display) was \(w.value(v)) on \(w.date(v.date)), \(side) the range \(w.range(v)).",
          "Mein Wert \(v.display) lag am \(w.date(v.date)) bei \(w.value(v)), \(side) dem Bereich \(w.range(v)).")
        if let t {
          text += s(" Before: \(w.value(t.first)) on \(w.date(t.first.date)).",
                    " Zuvor: \(w.value(t.first)) am \(w.date(t.first.date)).")
        }
        return text + s(" What does it mean for me, and when should it be checked again?",
                        " Was bedeutet das für mich, und wann sollte er erneut kontrolliert werden?")
      case .rising(let t):
        return s(
          "My \(t.display) rose from \(w.value(t.first)) (\(w.date(t.first.date))) to \(w.value(t.last)) (\(w.date(t.last.date))). Is this rise relevant?",
          "Mein Wert \(t.display) stieg von \(w.value(t.first)) (\(w.date(t.first.date))) auf \(w.value(t.last)) (\(w.date(t.last.date))). Ist dieser Anstieg von Bedeutung?")
      case .test(let name):
        return s("Would this test make sense for me: \(name)?", "Wäre diese Untersuchung für mich sinnvoll: \(name)?")
      case .unanswered(let open):
        return s("Questions of my anamnesis I could not answer yet: ", "Fragen meiner Anamnese, die ich noch nicht beantworten konnte: ")
          + open.joined(separator: " / ") + s(" Do they matter for you?", " Sind sie für Sie wichtig?")
      }
    }
    sections.append(Section(
      title: s("Questions for the doctor", "Fragen an die Ärztin oder den Arzt"),
      blocks: asks.isEmpty
        ? [.paragraph(s("No question follows from my records.", "Aus meinen Unterlagen ergibt sich keine Frage."), note: true)]
        : [.list(asks, ordered: true)]))

    let footer = s(
      "Not a diagnosis and not medical advice. Every lab value is quoted from the paper report named with it (date, lab, the printed line) and can be checked there; guideline ranges come from the source named. Apple Watch values are the device's weekly means, not measurements in a practice. Prepared with Klarbefund, on the patient's own device.",
      "Keine Diagnose und keine medizinische Beratung. Jeder Laborwert ist aus dem genannten Papierbefund übernommen (Datum, Labor, gedruckte Zeile) und dort nachprüfbar; Leitlinienbereiche stammen aus der genannten Quelle. Werte der Apple Watch sind Wochenmittel des Geräts, keine Messungen in der Praxis. Erstellt mit Klarbefund, auf dem eigenen Gerät des Patienten.")
    return Content(title: title, subtitle: subtitle, meta: meta, sections: sections, footer: footer)
  }

  // MARK: HTML

  static func escape(_ s: String) -> String {
    s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
      .replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;")
  }

  static let css = """
    @page { size: A4; margin: 16mm 15mm 18mm 15mm; }
    * { box-sizing: border-box; }
    html { background: #ffffff; }
    body { margin: 0 auto; max-width: 180mm; padding: 8mm 0; color: #1c1d21; background: #ffffff;
      font: 10pt/1.4 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; }
    @media print { body { padding: 0; max-width: none; } }
    header { border-bottom: 2px solid #1f4e79; padding-bottom: 3mm; margin-bottom: 4mm; }
    h1 { font-size: 17pt; margin: 0 0 1mm; color: #1f4e79; }
    .sub { margin: 0; color: #4a4d55; }
    table.meta { margin-top: 3mm; border: none; width: auto; }
    table.meta td { border: none; padding: 0 6mm 0 0; }
    table.meta td:first-child { color: #4a4d55; }
    h2 { font-size: 12pt; color: #1f4e79; margin: 6mm 0 2mm; padding-bottom: 1mm; border-bottom: 1px solid #c9d3df;
      break-after: avoid; page-break-after: avoid; }
    h3 { font-size: 10pt; margin: 3mm 0 1.5mm; break-after: avoid; page-break-after: avoid; }
    table { width: 100%; border-collapse: collapse; margin: 0 0 2mm; font-size: 8.8pt; }
    th { text-align: left; background: #eef2f7; color: #1c1d21; font-weight: 600; }
    th, td { border: 1px solid #d5dae1; padding: 1.2mm 1.6mm; vertical-align: top; }
    tr { break-inside: avoid; page-break-inside: avoid; }
    thead { display: table-header-group; }
    td.flag { font-weight: 700; color: #a4262c; }
    td.date { white-space: nowrap; }
    td.mono { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 8pt; color: #3a3d44; }
    div.keep { break-inside: avoid; page-break-inside: avoid; }
    p { margin: 0 0 2mm; }
    p.note { color: #5a5e67; font-size: 8.5pt; }
    ul, ol { margin: 0 0 2mm; padding-left: 6mm; }
    li { margin-bottom: 1mm; break-inside: avoid; page-break-inside: avoid; }
    footer { margin-top: 7mm; padding-top: 2mm; border-top: 1px solid #c9d3df; color: #5a5e67; font-size: 8pt; }
    """

  /// A printable A4 page: inline CSS, no script, nothing loaded from anywhere.
  public func html(language: Language) -> String {
    let c = content(language)
    let e = Self.escape
    var out = [
      "<!doctype html>", "<html lang=\"\(language.rawValue)\">", "<head>", "<meta charset=\"utf-8\">",
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
      "<title>\(e(c.title))</title>", "<style>\(Self.css)</style>", "</head>", "<body>",
      "<header>", "<h1>\(e(c.title))</h1>", "<p class=\"sub\">\(e(c.subtitle))</p>", "<table class=\"meta\">",
    ]
    out += c.meta.map { "<tr><td>\(e($0.0))</td><td>\(e($0.1))</td></tr>" }
    out += ["</table>", "</header>"]
    for (i, section) in c.sections.enumerated() {
      out.append("<section>")
      // The heading stays on the page of its first table, list or text, with the notes and the
      // subheading before it (WebKit ignores break-after: avoid).
      let keep = section.blocks.firstIndex { block in
        switch block {
        case .heading, .paragraph(_, note: true): return false
        default: return true
        }
      } ?? section.blocks.count - 1
      out.append("<div class=\"keep\">")
      out.append("<h2>\(i + 1). \(e(section.title))</h2>")
      for (k, block) in section.blocks.enumerated() {
        if k == keep + 1 { out.append("</div>") }
        switch block {
        case .paragraph(let text, let note):
          out.append(note ? "<p class=\"note\">\(e(text))</p>" : "<p>\(e(text))</p>")
        case .heading(let text):
          out.append("<h3>\(e(text))</h3>")
        case .list(let items, let ordered):
          let tag = ordered ? "ol" : "ul"
          out.append("<\(tag)>" + items.map { "<li>\(e($0))</li>" }.joined() + "</\(tag)>")
        case .table(let head, let rows):
          var t = "<table><thead><tr>" + head.map { "<th>\(e($0))</th>" }.joined() + "</tr></thead><tbody>"
          for row in rows {
            t += "<tr>"
            for (j, cell) in row.enumerated() {
              let mono = j == row.count - 1 && head.count >= 4 && (head.last == "As printed" || head.last == "Gedruckte Zeile")
              let date = cell.text.count == 10 && cell.text.allSatisfy { $0.isNumber || $0 == "-" || $0 == "." }
              let cls = cell.strong ? " class=\"flag\"" : mono ? " class=\"mono\"" : date ? " class=\"date\"" : ""
              t += "<td\(cls)>\(e(cell.text))</td>"
            }
            t += "</tr>"
          }
          out.append(t + "</tbody></table>")
        }
      }
      if keep + 1 >= section.blocks.count { out.append("</div>") }
      out.append("</section>")
    }
    out += ["<footer>\(e(c.footer))</footer>", "</body>", "</html>"]
    return out.joined(separator: "\n")
  }

  // MARK: Markdown

  /// The same letter as Markdown (for the MCP tool and for pasting).
  public func markdown(language: Language) -> String {
    let c = content(language)
    func cell(_ s: String) -> String {
      s.replacingOccurrences(of: "|", with: "\\|").replacingOccurrences(of: "\n", with: " ")
    }
    var out = ["# \(c.title)", "", "_\(c.subtitle)_", ""]
    out += c.meta.map { "- **\($0.0):** \($0.1)" }
    for (i, section) in c.sections.enumerated() {
      out += ["", "## \(i + 1). \(section.title)", ""]
      for block in section.blocks {
        switch block {
        case .paragraph(let text, let note):
          out += [note ? "_\(text)_" : text, ""]
        case .heading(let text):
          out += ["### \(text)", ""]
        case .list(let items, let ordered):
          out += items.enumerated().map { ordered ? "\($0.offset + 1). \($0.element)" : "- \($0.element)" }
          out.append("")
        case .table(let head, let rows):
          out.append("| " + head.map(cell).joined(separator: " | ") + " |")
          out.append("|" + String(repeating: " --- |", count: head.count))
          for row in rows {
            out.append("| " + row.map { $0.strong ? "**\(cell($0.text))**" : cell($0.text) }.joined(separator: " | ") + " |")
          }
          out.append("")
        }
      }
    }
    out += ["---", "", "_\(c.footer)_", ""]
    return out.joined(separator: "\n")
  }
}
