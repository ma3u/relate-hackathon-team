import Foundation

/// The German texts of the anamnesis and its protocols (`health_graph/german.py`, generated into
/// AnamnesisData.swift and ProtocolData.swift under "de"): questions, answer labels, protocol names,
/// bands, findings and the tests the plan suggests. Stored answers keep their linkId, codes and English
/// labels; these only change what a German reader sees. Every lookup returns nil where German has no
/// text, so the caller keeps the stored English.
public enum German {
  nonisolated(unsafe) static let anamnesis: JSONObject = Anamnesis.data.object("de") ?? [:]
  nonisolated(unsafe) static let protocols: JSONObject = Protocols.data.object("de") ?? [:]

  /// A date as German writes it: 2026-09-04 → 04.09.2026.
  public static func date(_ iso: String) -> String {
    let d = String(iso.prefix(10))
    let p = d.split(separator: "-")
    return p.count == 3 ? "\(p[2]).\(p[1]).\(p[0])" : d
  }

  static func protocolTexts(_ id: String) -> JSONObject? { protocols.object("protocols")?.object(id) }

  /// The German item: the protocol's when one is named, else the data-driven anamnesis's, else the first
  /// protocol that asks this question (a protocol answer read without its protocol, such as `smoking`).
  static func item(_ linkId: String, protocolId: String?) -> JSONObject? {
    if let protocolId, let it = protocolTexts(protocolId)?.object("items")?.object(linkId) { return it }
    if let it = anamnesis.object("items")?.object(linkId) { return it }
    for id in Protocols.ids { if let it = protocolTexts(id)?.object("items")?.object(linkId) { return it } }
    return nil
  }

  /// Where a question is defined, in English: the named protocol, else the data-driven anamnesis and
  /// every protocol that asks it (a stored label is matched in each until one fits).
  static func definitions(_ linkId: String, protocolId: String?) -> [(protocolId: String?, options: [(code: String, label: String)])] {
    func protocolOptions(_ id: String) -> [(code: String, label: String)]? {
      guard let p = Protocols.definition(id), let it = Protocols.items(p).first(where: { $0.string("linkId") == linkId })
      else { return nil }
      return Protocols.options(it).compactMap { o in o.string("code").map { ($0, o.string("label") ?? $0) } }
    }
    if let protocolId, let o = protocolOptions(protocolId) { return [(protocolId, o)] }
    var out: [(protocolId: String?, options: [(code: String, label: String)])] = []
    if let it = Anamnesis.item(linkId) {
      out.append((nil, (it["options"] as? [[Any]] ?? []).compactMap { o in
        guard o.count == 3, let c = o[0] as? String, let l = o[1] as? String else { return nil }
        return (c, l)
      }))
    }
    for id in Protocols.ids { if let o = protocolOptions(id) { out.append((id, o)) } }
    return out
  }

  /// A question's German text, `{date}` filled with the German date of `context` (or "an dem Tag").
  public static func question(_ linkId: String, protocolId: String? = nil, context: String? = nil) -> String? {
    guard let text = item(linkId, protocolId: protocolId)?.text("text") else { return nil }
    let fallback = anamnesis.string("dateFallback") ?? "an dem Tag"
    return text.replacingOccurrences(of: "{date}", with: context.map(date) ?? fallback)
  }

  /// An answer option's German label, by its code.
  public static func label(_ linkId: String, protocolId: String? = nil, code: String) -> String? {
    item(linkId, protocolId: protocolId)?.object("options")?.text(code)
  }

  /// The German labels of a stored answer: by its codes, else by its English labels matched against
  /// the question's options. Nil when one of them has no German label.
  public static func labels(_ linkId: String, protocolId: String? = nil, codes: [String], english: [String])
    -> [String]?
  {
    if !codes.isEmpty {
      let de = codes.compactMap { label(linkId, protocolId: protocolId, code: $0) }
      return de.count == codes.count ? de : nil
    }
    for d in definitions(linkId, protocolId: protocolId) {
      let de = english.compactMap { e in
        d.options.first { $0.label == e }.flatMap { label(linkId, protocolId: d.protocolId, code: $0.code) }
      }
      if de.count == english.count { return de }
    }
    return nil
  }

  public static func protocolName(_ id: String) -> String? { protocolTexts(id)?.text("name") }
  public static func protocolTitle(_ id: String) -> String? { protocolTexts(id)?.text("title") }
  public static func protocolWhy(_ id: String) -> String? { protocolTexts(id)?.text("why") }
  public static func protocolCritical(_ id: String) -> [String]? { protocolTexts(id)?["critical"] as? [String] }

  /// A band's German label: a scored band by its place among the protocol's bands, else the band
  /// of the family history or the plant-based summary.
  public static func band(_ protocolId: String, _ english: String) -> String? {
    if let p = Protocols.definition(protocolId), let bands = p["bands"] as? [[Any]],
      let i = bands.firstIndex(where: { $0.count == 3 && ($0[1] as? String) == english }),
      let de = protocolTexts(protocolId)?["bands"] as? [[String]], i < de.count, let label = de[i].first
    {
      return label
    }
    return protocols.object("summaryBands")?.text(english)
  }

  /// A band's German meaning (scored protocols only).
  public static func bandMeaning(_ protocolId: String, _ english: String) -> String? {
    guard let p = Protocols.definition(protocolId), let bands = p["bands"] as? [[Any]],
      let i = bands.firstIndex(where: { $0.count == 3 && ($0[1] as? String) == english }),
      let de = protocolTexts(protocolId)?["bands"] as? [[String]], i < de.count, de[i].count > 1
    else { return nil }
    return de[i][1]
  }

  /// Where a prefill comes from (protocols.PREFILL), in German.
  public static func prefill(_ key: String) -> String? { protocols.object("prefill")?.text(key) }

  /// A finding's German title or why, by the rule's id.
  public static func rule(_ id: String, _ key: String) -> String? { anamnesis.object("rules")?.object(id)?.text(key) }

  /// An analyte group's German name.
  public static func group(_ id: String) -> String? { anamnesis.object("groups")?.text(id) }

  /// A test the plan suggests (a rule's `tests` or `ifMissing`), in German, by its English text.
  public static func test(_ english: String) -> String? {
    for rule in Anamnesis.rules {
      guard let id = rule.string("id"), let de = anamnesis.object("rules")?.object(id) else { continue }
      if let tests = rule["tests"] as? [String], let i = tests.firstIndex(of: english),
        let deTests = de["tests"] as? [String], i < deTests.count
      {
        return deTests[i]
      }
      if let missing = rule["ifMissing"] as? [String: String],
        let group = missing.first(where: { $0.value == english })?.key
      {
        return de.object("ifMissing")?.text(group)
      }
    }
    return nil
  }
}
