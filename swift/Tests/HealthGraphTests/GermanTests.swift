import Foundation
import Testing

@testable import HealthGraph

/// The anamnesis in German (health_graph/german.py, generated into the Swift data): every question and
/// answer of the data-driven anamnesis and of every protocol has a German text, the German plan and the
/// German letter use them, and linkIds, codes and scores stay what they were.
@Suite("German anamnesis", .serialized)
struct GermanTests {
  @Test func everyAnamnesisQuestionAndAnswerHasItsGermanText() {
    #expect(!Anamnesis.items.isEmpty)
    for item in Anamnesis.items {
      let link = item.string("linkId") ?? ""
      let de = German.question(link, context: "2026-09-04")
      #expect(de?.isEmpty == false, "no German text for \(link)")
      #expect(de?.contains("{date}") == false)
      for o in item["options"] as? [[Any]] ?? [] {
        let code = o[0] as? String ?? ""
        #expect(German.label(link, code: code)?.isEmpty == false, "no German label for \(link) \(code)")
      }
    }
    for rule in Anamnesis.rules {
      let id = rule.string("id") ?? ""
      #expect(German.rule(id, "title") != nil && German.rule(id, "why") != nil, "rule \(id)")
      for t in (rule["tests"] as? [String] ?? []) + ((rule["ifMissing"] as? [String: String])?.values.map { $0 } ?? []) {
        #expect(German.test(t) != nil, "no German test for \(t)")
      }
    }
  }

  @Test func everyProtocolQuestionAndAnswerHasItsGermanText() {
    #expect(Protocols.ids.count == 10)
    for p in Protocols.definitions {
      let id = p.string("id") ?? ""
      #expect(German.protocolName(id) != nil && German.protocolTitle(id) != nil && German.protocolWhy(id) != nil, "\(id)")
      #expect(German.protocolCritical(id)?.count == (p["critical"] as? [String] ?? []).count, "\(id) critical")
      for band in p["bands"] as? [[Any]] ?? [] {
        let label = band[1] as? String ?? ""
        #expect(German.band(id, label) != nil && German.bandMeaning(id, label) != nil, "\(id) band \(label)")
      }
      for item in Protocols.items(p) {
        let link = item.string("linkId") ?? ""
        #expect(German.question(link, protocolId: id)?.isEmpty == false, "\(id) \(link)")
        for o in Protocols.options(item) {
          let code = o.string("code") ?? ""
          #expect(German.label(link, protocolId: id, code: code)?.isEmpty == false, "\(id) \(link) \(code)")
        }
      }
    }
    for (key, _) in Protocols.data.object("prefillText") ?? [:] { #expect(German.prefill(key) != nil, "prefill \(key)") }
    for band in ["none", "premature", "age unknown", "later in life", "vegan", "pesco-vegetarian", "vegetarian"] {
      #expect(German.band("family-cvd", band) != nil || German.band("plant-based", band) != nil, "\(band)")
    }
  }

  @Test func storedEnglishLabelsFindTheirGermanOnes() {
    #expect(German.labels("smoking", codes: [], english: ["Never"]) == ["Nie"])
    // a protocol's own wording, read without its protocol
    #expect(German.labels("smoking", codes: [], english: ["Current smoker, even occasionally"]) == ["Ich rauche, auch gelegentlich"])
    #expect(German.labels("audit-c-1", protocolId: "audit-c", codes: ["2-4-month"], english: []) == ["2- bis 4-mal pro Monat"])
    #expect(German.labels("smoking", codes: [], english: ["Something else"]) == nil)
    #expect(German.band("audit-c", "at or above the cut-off") == "am oder über dem Grenzwert")
    #expect(German.date("2026-09-04") == "04.09.2026")
  }

  @Test func theGermanPlanAsksTheSameQuestionsInGerman() throws {
    let store = try DoctorLetterTests.store()
    let en = try store.anamnesisPlan(today: DoctorLetterTests.today)
    let de = try store.anamnesisPlan(today: DoctorLetterTests.today, language: .de)
    let keys = { (p: JSONObject) in (p["questions"] as? [JSONObject] ?? []).compactMap { $0.string("key") } }
    let codes = { (p: JSONObject) in
      (p["questions"] as? [JSONObject] ?? []).map { ($0["options"] as? [JSONObject] ?? []).compactMap { $0.string("code") } }
    }
    #expect(!keys(en).isEmpty && keys(en) == keys(de) && codes(en) == codes(de))
    #expect((de["findings"] as? [JSONObject] ?? []).map { $0.string("id") } == (en["findings"] as? [JSONObject] ?? []).map { $0.string("id") })
    let texts = (de["questions"] as? [JSONObject] ?? []).compactMap { $0.string("text") }
    #expect(texts.allSatisfy { t in !(en["questions"] as? [JSONObject] ?? []).contains { $0.string("text") == t } })
    for f in de["findings"] as? [JSONObject] ?? [] {
      #expect(f.string("title") == German.rule(f.string("id") ?? "", "title"))
    }
    // The answers given to the German plan are the same answers: same keys, same codes, English labels stored.
    let checked = try Anamnesis.validate(["smoking": "never"])
    #expect(checked.count == 1)
  }

  @Test func theGermanProtocolPlanScoresAlike() throws {
    let store = try DoctorLetterTests.store()
    let en = try store.protocolPlan(today: DoctorLetterTests.today, birthYear: 1972, sex: "male")
    let de = try store.protocolPlan(today: DoctorLetterTests.today, birthYear: 1972, sex: "male", language: .de)
    let ps = { (p: JSONObject) in p["protocols"] as? [JSONObject] ?? [] }
    #expect(ps(en).map { $0.string("id") } == ps(de).map { $0.string("id") })
    for (a, b) in zip(ps(en), ps(de)) {
      #expect((a["items"] as? [JSONObject] ?? []).map { $0.string("linkId") } == (b["items"] as? [JSONObject] ?? []).map { $0.string("linkId") })
      #expect(NSDictionary(dictionary: a["score"] as? JSONObject ?? [:]).isEqual(to: b["score"] as? JSONObject ?? [:]))
    }
    let findrisc = try #require(ps(de).first { $0.string("id") == "findrisc" })
    let age = try #require((findrisc["items"] as? [JSONObject])?.first { $0.string("linkId") == "findrisc-age" })
    #expect(age.string("text") == "Wie alt sind Sie?")
    #expect((age["prefilled"] as? JSONObject)?.string("code") == "45-54")
    #expect((age["prefilled"] as? JSONObject)?.string("text") == "Geburtsjahr 1972")
    #expect(ps(de).first { $0.string("id") == "tobacco" }?.string("name") == "Tabakkonsum")
  }

  @Test func theGermanLetterQuotesGermanQuestionsAndAnswers() throws {
    let store = try DoctorLetterTests.store()
    try store.storeProtocol("audit-c", ["audit-c-1": "2-4-month", "audit-c-2": "1-2", "audit-c-3": "never"],
                            source: "mac-app", authored: "2026-11-11T09:00:00Z")
    let letter = try store.doctorLetter(.gp, today: DoctorLetterTests.today)
    let audit = try #require(letter.answers.first { $0.linkId == "audit-c-1" })
    #expect(audit.codes == ["2-4-month"] && audit.labels == ["2 to 4 times a month"])  // stored as before
    #expect(letter.scores.first { $0.protocolId == "audit-c" }?.score == "2")
    let de = letter.markdown(language: .de), en = letter.markdown(language: .en)
    #expect(de.contains("Rauchen Sie, oder haben Sie früher geraucht? | Nie | never smoked"))
    #expect(de.contains("AUDIT-C: Wie oft trinken Sie Alkohol? | 2- bis 4-mal pro Monat"))
    #expect(de.contains("Meine Angabe (10.11.2026): Wie viel Bewegung, bei der Sie schneller atmen"))
    #expect(de.contains("| AUDIT-C | 2 | unter dem Grenzwert |"))
    #expect(!de.contains("englisch"))  // everything was translated: no note
    #expect(!de.contains("How often do you have a drink") && !de.contains("Do you smoke"))
    #expect(en.contains("AUDIT-C: How often do you have a drink containing alcohol? | 2 to 4 times a month"))
    #expect(en.contains("| AUDIT-C | 2 | below the cut-off |"))
    // the plan's tests and open questions, in German
    #expect(de.contains("Wäre diese Untersuchung für mich sinnvoll: Lp(a), einmal im Leben"))
    #expect(de.contains("Fragen meiner Anamnese, die ich noch nicht beantworten konnte: "))
  }

  @Test func anAnswerWithoutAGermanTextIsQuotedAsStoredWithTheNote() {
    let a = DoctorLetter.Answer(
      linkId: "an-old-question", question: "A question an older version asked", labels: ["Yes"], text: nil,
      context: nil, authored: "2026-11-10", protocolId: nil, protocolName: nil, riskFactor: false)
    let w = DoctorLetter.Words(language: .de)
    #expect(w.question(a) == "A question an older version asked" && w.labels(a) == ["Yes"] && !w.translated(a))
  }
}
