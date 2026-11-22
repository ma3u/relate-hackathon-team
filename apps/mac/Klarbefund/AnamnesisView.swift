import HealthGraph
import SwiftUI

/// The anamnesis, natively on the Mac: what stands out in your own values and only the questions
/// it leaves (HealthGraph's anamnesis plan), then the validated protocols one at a time, prefilled
/// from your earlier answers and year of birth. Read from Claude's read-only snapshot; saving hands
/// the answers to the app, which checks and stores them in the graph it owns (source "mac-app"). In the
/// app's language: German questions and answers (HealthGraph's German texts) when the Mac prefers German;
/// the answers are stored as before, by linkId and code.
struct AnamnesisView: View {
  @ObservedObject var model: AppModel
  @ObservedObject var state: AnamnesisState

  enum Pane: Hashable {
    case values
    case protocolId(String)
  }

  @State private var pane: Pane = .values

  var body: some View {
    HStack(spacing: 0) {
      scrolling { sidebar.padding(12) }.frame(width: 270)
      Divider()
      scrolling { detail.padding(20).frame(maxWidth: 760, alignment: .leading) }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }
    .frame(minWidth: 900, minHeight: 600)
    .task(id: model.snapshotVersion) { state.reload() }
  }

  /// ImageRenderer draws no scroll view: the docs render lays the content out directly.
  @ViewBuilder private func scrolling<V: View>(@ViewBuilder _ content: () -> V) -> some View {
    if renderingForDocs {
      let view = content()
      GeometryReader { g in  // top-left, cut at the window's bottom edge as a scroll view would
        view.fixedSize(horizontal: false, vertical: true).frame(width: g.size.width, alignment: .topLeading)
      }
      .clipped()
    } else {
      ScrollView(.vertical) { content().frame(maxWidth: .infinity, alignment: .leading) }
    }
  }

  // MARK: Sidebar

  @ViewBuilder private var sidebar: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text("Anamnesis").font(.title2.bold()).padding(.bottom, 6)
      entry(.values, String(localized: "From your values"), detail: state.questions.isEmpty
        ? String(localized: "Nothing open") : String(localized: "\(state.questions.count) open questions"),
        symbol: "waveform.path.ecg")
      Text("Protocols").font(.caption.weight(.semibold)).foregroundStyle(.secondary).padding(.top, 10)
      ForEach(state.protocols, id: \.id) { p in
        entry(.protocolId(p.id), p.name, detail: p.status, symbol: p.answered ? "checkmark.circle" : "list.bullet.clipboard")
      }
    }
  }

  @ViewBuilder private func entry(_ target: Pane, _ title: String, detail: String, symbol: String) -> some View {
    let row = HStack(alignment: .firstTextBaseline, spacing: 8) {
      Image(systemName: symbol).frame(width: 18)
      VStack(alignment: .leading, spacing: 1) {
        Text(title).lineLimit(2)
        Text(detail).font(.caption).foregroundStyle(.secondary)
      }
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 8).padding(.vertical, 6)
    .background(pane == target ? Color.accentColor.opacity(0.18) : .clear, in: RoundedRectangle(cornerRadius: 7))
    .contentShape(Rectangle())
    if renderingForDocs {
      row
    } else {
      Button { pane = target } label: { row }.buttonStyle(.plain)
    }
  }

  // MARK: Detail

  @ViewBuilder private var detail: some View {
    if let problem = state.problem {
      Label(problem, systemImage: "exclamationmark.triangle").foregroundStyle(.secondary)
    } else {
      switch pane {
      case .values: valuesPane
      case .protocolId(let id):
        if let p = state.protocols.first(where: { $0.id == id }) { protocolPane(p) }
      }
    }
  }

  @ViewBuilder private var valuesPane: some View {
    VStack(alignment: .leading, spacing: 16) {
      VStack(alignment: .leading, spacing: 4) {
        Text("From your values").font(.title2.bold())
        Text("Only what your lab values and Apple Watch data cannot tell. Your answers are stored in your health graph and appear in your doctor's letter.")
          .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
      }
      if !state.findings.isEmpty {
        Card(title: "What stands out", symbol: "exclamationmark.circle") {
          ForEach(state.findings, id: \.self) { Text($0).fixedSize(horizontal: false, vertical: true) }
        }
      }
      if !state.known.isEmpty {
        Card(title: "Already known, not asked again", symbol: "checkmark.seal") {
          ForEach(state.known, id: \.self) {
            Text($0).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
          }
        }
      }
      if state.questions.isEmpty {
        Label("Your data and your earlier answers answer everything this plan asks.", systemImage: "checkmark.circle")
          .foregroundStyle(.secondary)
      }
      ForEach(state.questions) { q in
        QuestionCard(question: q, selected: binding(q.key), text: textBinding(q.key))
      }
      if !state.questions.isEmpty {
        SaveRow(title: "Save answers", enabled: state.hasAnswers, message: state.message, failed: state.failed) {
          state.saveValues(model)
        }
      }
    }
  }

  @ViewBuilder private func protocolPane(_ p: AnamnesisState.ProtocolForm) -> some View {
    VStack(alignment: .leading, spacing: 16) {
      VStack(alignment: .leading, spacing: 4) {
        Text(p.name).font(.title2.bold())
        if let title = p.title, title != p.name { Text(title).foregroundStyle(.secondary) }
        if let why = p.why { Text(why).fixedSize(horizontal: false, vertical: true).padding(.top, 4) }
        Text(p.status).font(.callout).foregroundStyle(.secondary)
      }
      ForEach(p.items.filter { state.enabled($0, in: p.id) }) { q in
        QuestionCard(question: q, selected: binding(q.key, protocolId: p.id), text: textBinding(q.key, protocolId: p.id))
      }
      SaveRow(title: "Save \(p.name)", enabled: state.hasAnswers(p.id), message: state.message, failed: state.failed) {
        state.saveProtocol(p.id, model)
      }
      if let source = p.source {
        Text(source).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private func binding(_ key: String, protocolId: String? = nil) -> Binding<Set<String>> {
    Binding(get: { state.choice(key, protocolId) }, set: { state.setChoice(key, protocolId, $0) })
  }

  private func textBinding(_ key: String, protocolId: String? = nil) -> Binding<String> {
    Binding(get: { state.words(key, protocolId) }, set: { state.setWords(key, protocolId, $0) })
  }
}

// MARK: The state behind the window

@MainActor
final class AnamnesisState: ObservableObject {
  /// The Anamnesis window's state, kept while the app runs so answers in progress survive closing it.
  static let shared = AnamnesisState()

  struct Option: Hashable {
    let code: String, label: String
  }

  struct Question: Identifiable {
    var id: String { key }
    let key: String
    let linkId: String
    let text: String
    let options: [Option]
    let multiple: Bool
    let month: Bool
    /// Where a prefilled answer comes from, shown under the question.
    var prefilled: String?
    var enableWhen: [String: [String]] = [:]
    var basedOn: [String] = []
    var findings: [String] = []
  }

  struct ProtocolForm: Identifiable {
    let id: String
    let name: String
    let title: String?
    let why: String?
    let source: String?
    let status: String
    let answered: Bool
    let items: [Question]
  }

  /// The snapshot to read: Claude's, or a synthetic store for the docs render.
  let source: URL?
  let today: String?

  @Published var findings: [String] = []
  @Published var known: [String] = []
  @Published var questions: [Question] = []
  @Published var protocols: [ProtocolForm] = []
  @Published var problem: String?
  @Published var message: String?
  /// The last save was refused (the message says why).
  @Published var failed = false

  @Published private var choices: [String: Set<String>] = [:]
  @Published private var texts: [String: String] = [:]
  private var prefilledFrom: [String: String] = [:]

  init(source: URL? = Paths.snapshot, today: String? = nil) {
    self.source = source
    self.today = today
  }

  private static func slot(_ key: String, _ protocolId: String?) -> String { "\(protocolId ?? "plan")/\(key)" }
  func choice(_ key: String, _ p: String?) -> Set<String> { choices[Self.slot(key, p)] ?? [] }
  func setChoice(_ key: String, _ p: String?, _ v: Set<String>) {
    choices[Self.slot(key, p)] = v
    prefilledFrom[Self.slot(key, p)] = nil  // changed by hand: no longer prefilled
  }
  func words(_ key: String, _ p: String?) -> String { texts[Self.slot(key, p)] ?? "" }
  func setWords(_ key: String, _ p: String?, _ v: String) { texts[Self.slot(key, p)] = v }

  var hasAnswers: Bool { questions.contains { !choice($0.key, nil).isEmpty || !words($0.key, nil).isEmpty } }
  func hasAnswers(_ p: String) -> Bool {
    protocols.first { $0.id == p }?.items.contains { !choice($0.key, p).isEmpty || !words($0.key, p).isEmpty } ?? false
  }

  /// A protocol question applies when its enableWhen holds for the answers chosen so far.
  func enabled(_ q: Question, in p: String) -> Bool {
    q.enableWhen.allSatisfy { link, wants in !choice(link, p).isDisjoint(with: wants) }
  }

  func reload() {
    let source = source, today = today ?? ISO8601DateFormatter.string(from: Date(), timeZone: .current, formatOptions: [.withFullDate])
    let language = AppLanguage.current
    do {
      let (plan, protocolPlan) = try Snapshot.read(source) { store -> (JSONObject, JSONObject) in
        let person = try store.rows(cypher: "MATCH (p:Patient) RETURN p.birthYear AS y, p.gender AS g").first ?? [:]
        return (try store.anamnesisPlan(today: today, language: language),
                try store.protocolPlan(today: today, birthYear: person["y"].flatMap { Int($0) },
                                       sex: person["g"].flatMap { $0.isEmpty ? nil : $0 }, language: language))
      }
      problem = nil
      apply(plan: plan, protocolPlan: protocolPlan)
    } catch {
      problem = "\(error)"
    }
  }

  private func apply(plan: JSONObject, protocolPlan: JSONObject) {
    let language = AppLanguage.current
    findings = (plan["findings"] as? [JSONObject] ?? []).map { f in
      let values = (f["values"] as? [JSONObject] ?? []).map { v in
        let value = language == .de ? Self.plain(v["value"]).replacingOccurrences(of: ".", with: ",") : Self.plain(v["value"])
        let display = v["display"] as? String ?? "", unit = v["unit"] as? String ?? ""
        let day = AppLanguage.day(v["date"] as? String ?? "")
        return String(localized: "\(display) \(value) \(unit) on \(day)")
      }
      let title = f["title"] as? String ?? ""
      return values.isEmpty ? title : "\(title): \(values.joined(separator: "; "))"
    }
    known = (plan["known"] as? [JSONObject] ?? []).compactMap { $0["detail"] as? String }
      + (plan["skipped"] as? [JSONObject] ?? []).compactMap { s in
        (s["reason"] as? String).map { reason in
          let link = s["linkId"] as? String ?? ""
          let key = s["key"] as? String ?? link
          let context = key.contains("@") ? String(key.split(separator: "@", maxSplits: 1)[1]) : nil
          return "\(Anamnesis.questionText(link, context: context, language: language) ?? link) (\(reason))"
        }
      }
    questions = (plan["questions"] as? [JSONObject] ?? []).map { q in
      Question(
        key: q["key"] as? String ?? "", linkId: q["linkId"] as? String ?? "", text: q["text"] as? String ?? "",
        options: Self.options(q["options"]), multiple: (q["multiple"] as? Bool) ?? false, month: false,
        basedOn: q["basedOn"] as? [String] ?? [], findings: q["findings"] as? [String] ?? [])
    }
    protocols = (protocolPlan["protocols"] as? [JSONObject] ?? []).map { p in
      let id = p["id"] as? String ?? ""
      let items: [Question] = (p["items"] as? [JSONObject] ?? []).map { it in
        let link = it["linkId"] as? String ?? ""
        var q = Question(
          key: link, linkId: link, text: it["text"] as? String ?? link, options: Self.options(it["options"]),
          multiple: (it["multiple"] as? Bool) ?? false, month: (it["type"] as? String) == "month")
        if let when = it["enableWhen"] as? JSONObject {
          q.enableWhen = when.mapValues { ($0 as? [String]) ?? [($0 as? String) ?? ""] }
        }
        if let pre = it["prefilled"] as? JSONObject {
          let slot = Self.slot(link, id)
          q.prefilled = pre["text"] as? String
          if choices[slot] == nil, let code = pre["code"] as? String { choices[slot] = [code] }
          if texts[slot] == nil, let value = pre["value"] as? String { texts[slot] = value }
          prefilledFrom[slot] = q.prefilled
        }
        return q
      }
      let last = p["lastAnswered"] as? JSONObject
      let lastDay = (last?["authored"] as? String).map { String($0.prefix(10)) }
      let band = (last?["band"] as? String).map { language == .de ? German.band(id, $0) ?? $0 : $0 }
      let prefilled = p["prefilled"] as? Int ?? 0
      let status = lastDay.map { String(localized: "Answered \(AppLanguage.day($0))") + (band.map { ", \($0)" } ?? "") }
        ?? (prefilled > 0 ? String(localized: "\(prefilled) of \(items.count) prefilled")
          : String(localized: "\(items.count) questions"))
      let source = [p["source"] as? String, (p["year"] as? Int).map(String.init)].compactMap { $0 }.joined(separator: ", ")
      return ProtocolForm(
        id: id, name: p["name"] as? String ?? id, title: p["title"] as? String, why: p["why"] as? String,
        source: source.isEmpty ? nil : String(localized: "Source: \(source)"), status: status, answered: lastDay != nil,
        items: items)
    }
  }

  static func options(_ any: Any?) -> [Option] {
    (any as? [JSONObject] ?? []).compactMap { o in
      guard let code = o["code"] as? String else { return nil }
      return Option(code: code, label: o["label"] as? String ?? code)
    }
  }

  static func plain(_ any: Any?) -> String {
    switch any {
    case let d as Double: return d == d.rounded() ? String(Int(d)) : String(d)
    case let i as Int: return String(i)
    case let s as String: return s
    default: return ""
    }
  }

  /// Hands the plan's answers to the app: {key: {codes, text, basedOn, findings}}. The question is stored
  /// as the anamnesis defines it (English), whatever language it was shown in; the letter translates it.
  func saveValues(_ model: AppModel) {
    var answers: [String: Any] = [:]
    for q in questions {
      let codes = q.options.map(\.code).filter { choice(q.key, nil).contains($0) }
      let text = words(q.key, nil).trimmingCharacters(in: .whitespacesAndNewlines)
      if codes.isEmpty && text.isEmpty { continue }
      var a: [String: Any] = ["codes": codes, "basedOn": q.basedOn, "findings": q.findings]
      if !text.isEmpty { a["text"] = text }
      answers[q.key] = a
    }
    report(model.storeAnamnesis(answers), clear: nil)
  }

  /// Hands one protocol's answers to the app, prefilled ones with where they came from.
  func saveProtocol(_ id: String, _ model: AppModel) {
    guard let p = protocols.first(where: { $0.id == id }) else { return }
    var answers: [String: Any] = [:]
    for q in p.items where enabled(q, in: id) {
      let slot = Self.slot(q.key, id)
      let text = words(q.key, id).trimmingCharacters(in: .whitespacesAndNewlines)
      var a: [String: Any] = [:]
      if q.month {
        if text.isEmpty { continue }
        a["text"] = text
      } else {
        let codes = q.options.map(\.code).filter { choice(q.key, id).contains($0) }
        if codes.isEmpty && text.isEmpty { continue }
        a["codes"] = codes
        if !text.isEmpty { a["text"] = text }
      }
      if let from = prefilledFrom[slot] { a["prefilled"] = from }
      answers[q.linkId] = a
    }
    report(model.storeProtocol(id, answers, source: "mac-app", from: "the Anamnesis window"), clear: id)
  }

  private func report(_ result: [String: Any], clear: String?) {
    if result["ok"] as? Bool == true {
      failed = false
      message = result["message"] as? String
      if clear == nil {  // answered questions leave the plan once the snapshot is refreshed
        for q in questions { choices[Self.slot(q.key, nil)] = nil; texts[Self.slot(q.key, nil)] = nil }
      }
    } else {
      failed = true
      message = String(localized: "Not stored: \(result["error"] as? String ?? String(localized: "unknown error"))")
    }
  }
}

// MARK: Pieces

private struct Card<Content: View>: View {
  let title: LocalizedStringKey, symbol: String
  @ViewBuilder var content: Content
  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      Label(title, systemImage: symbol).font(.headline)
      content
    }
    .padding(12).frame(maxWidth: .infinity, alignment: .leading)
    .background(.background.secondary, in: RoundedRectangle(cornerRadius: 10))
  }
}

/// One question: its options as rows to tick (one or several), and the person's own words.
private struct QuestionCard: View {
  let question: AnamnesisState.Question
  @Binding var selected: Set<String>
  @Binding var text: String

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(question.text).font(.body.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
      if let pre = question.prefilled {
        Label("Prefilled from \(pre)", systemImage: "wand.and.stars").font(.caption).foregroundStyle(.secondary)
      }
      if question.month {
        field(String(localized: "Year and month, e.g. 2024-03"))
      } else {
        ForEach(question.options, id: \.code) { o in option(o) }
        field(String(localized: "In your own words (optional)"))
      }
    }
    .padding(12).frame(maxWidth: .infinity, alignment: .leading)
    .background(.background.secondary, in: RoundedRectangle(cornerRadius: 10))
  }

  @ViewBuilder private func option(_ o: AnamnesisState.Option) -> some View {
    let on = selected.contains(o.code)
    let symbol = question.multiple ? (on ? "checkmark.square.fill" : "square") : (on ? "largecircle.fill.circle" : "circle")
    let row = HStack(spacing: 8) {
      Image(systemName: symbol).foregroundStyle(on ? Color.accentColor : .secondary)
      Text(o.label).fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 0)
    }
    .padding(.vertical, 3).contentShape(Rectangle())
    if renderingForDocs {
      row
    } else {
      Button {
        if question.multiple {
          if on { selected.remove(o.code) } else { selected.insert(o.code) }
        } else {
          selected = on ? [] : [o.code]
        }
      } label: { row }
      .buttonStyle(.plain)
    }
  }

  @ViewBuilder private func field(_ prompt: String) -> some View {
    if renderingForDocs {  // ImageRenderer draws no text field
      Text(text.isEmpty ? prompt : text).font(.callout).foregroundStyle(text.isEmpty ? .tertiary : .primary)
        .frame(maxWidth: .infinity, alignment: .leading).padding(6)
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
    } else {
      TextField(prompt, text: $text).textFieldStyle(.roundedBorder)
    }
  }
}

private struct SaveRow: View {
  let title: LocalizedStringKey
  let enabled: Bool
  let message: String?
  let failed: Bool
  let action: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      if renderingForDocs {
        Label(title, systemImage: "square.and.arrow.down").padding(.horizontal, 14).padding(.vertical, 7)
          .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 7)).foregroundStyle(.white)
      } else {
        Button(action: action) { Label(title, systemImage: "square.and.arrow.down") }
          .controlSize(.large).buttonStyle(.borderedProminent).disabled(!enabled)
      }
      Text("Checked and stored in your health graph on this Mac, coded with SNOMED CT where a code exists. Nothing is uploaded.")
        .font(.caption).foregroundStyle(.secondary)
      if let message {
        Label(message, systemImage: failed ? "xmark.octagon" : "checkmark.circle.fill")
          .foregroundStyle(failed ? .red : .green).textSelection(.enabled)
      }
    }
  }
}
