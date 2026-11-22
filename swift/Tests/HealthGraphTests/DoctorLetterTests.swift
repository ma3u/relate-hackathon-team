import Foundation
import Relate
import Testing

@testable import HealthGraph

/// The doctor's letter on the synthetic fixtures: its sections, a value seen twice counted once,
/// ranges only in the value's unit and valid on its date, the specialist's focus, both languages.
@Suite("Doctor's letter", .serialized)
struct DoctorLetterTests {
  static let today = "2026-11-15"

  /// The three synthetic reports, the knowledge layer, 60 synthetic Apple Watch weeks and two answers.
  static func store() throws -> HealthStore {
    let (store, _) = try Fixtures.loadedStore()
    try store.seedKnowledge()
    let patient = try store.singlePatient()
    var rows: [Row] = []
    for week in 0..<60 {
      let end = DoctorLetter.addDays("2026-11-08", -7 * week)
      let start = DoctorLetter.addDays(end, -6)
      let recent = week < 12
      for (code, unit, value, display) in [
        ("40443-4", "/min", recent ? 56.0 : 60.0, "Resting heart rate"),
        ("55411-3", "min/d", recent ? 40.0 : 25.0, "Exercise minutes"),
        ("94122-9", "mL/min/kg", recent ? 41.0 : 39.0, "VO2 max"),
      ] {
        rows.append([
          "resourceId": .string("\(patient)-wear-\(code)-\(start)"), "code": .string(code),
          "display": .string(display), "valueQuantity": .float(value), "unit": .string(unit),
          "effectiveStart": .string(start), "effectiveDate": .string(end), "category": "activity",
          "status": "final", "sourceKind": .string(FHIR.wearableSourceKind), "hubEligible": true,
        ])
      }
    }
    try store.importWearables(patientId: patient, rows: rows)
    try store.storeAnamnesis(
      ["smoking": ["codes": ["never"], "text": "never smoked"], "exercise": "2.5-5h"],
      source: "mac-app", authored: "2026-11-10T09:00:00Z")
    return store
  }

  @Test func theGPLetterHasEverySection() throws {
    let letter = try Self.store().doctorLetter(.gp, today: Self.today)
    #expect(letter.reportCount == 3 && letter.valueCount == 21)
    #expect(letter.latest.map(\.date) == ["2026-09-04"])
    #expect(letter.latest.first?.performer == "Praxis Dr. Muster")
    let ldl = try #require(letter.trends.first { $0.code == "2089-1" })
    #expect(ldl.values.map(\.date) == ["2026-03-12", "2026-06-10", "2026-09-04"])
    #expect(ldl.direction == .falling && ldl.last.flag == .high)
    #expect(ldl.last.guideline?.source.hasPrefix("ESC/EAS 2019") == true)
    #expect(ldl.last.sourceLine == "LDL-Cholesterin  141  mg/dl  < 116")
    // Apple Watch: the 12 weeks to the newest week against the 52 before.
    let rest = try #require(letter.vitals.first { $0.code == "40443-4" })
    #expect(rest.recentWeeks == 12 && rest.recentMean == 56 && rest.priorWeeks == 48 && rest.priorMean == 60)
    #expect(letter.window?.to == "2026-11-08")
    #expect(letter.activity.map(\.code) == ["55411-3", "94122-9"])
    #expect(letter.exerciseAnswer?.labels == ["2.5 to 5 hours"])
    #expect(letter.answers.first { $0.linkId == "smoking" }?.text == "never smoked")
    // Out-of-range values and the plan's tests become questions.
    #expect(letter.questions.contains { if case .outOfRange(let v, _) = $0 { return v.code == "2089-1" } else { return false } })
    #expect(letter.questions.contains { if case .test = $0 { return true } else { return false } })
  }

  @Test func aValueSeenInTwoReportsCountsOnce() throws {
    let store = try Self.store()
    try store.importReport(FHIR.parseBundle(DuplicateTests.asDigital(Fixtures.bundle(Fixtures.golden)), reportId: "rescan"))
    let letter = try store.doctorLetter(.gp, today: Self.today)
    #expect(letter.valueCount == 21)
    let hba1c = try #require(letter.trends.first { $0.code == "4548-4" })
    #expect(hba1c.values.map(\.date) == ["2026-03-12", "2026-06-10", "2026-09-04"])
    #expect(letter.latest.flatMap(\.values).filter { $0.code == "4548-4" }.count == 1)
  }

  @Test func aRangeAppliesOnlyInItsUnitAndOnItsDates() {
    typealias R = DoctorLetter.Range
    let old = R(low: nil, high: 130, unit: "mg/dL", sex: "any", validFrom: "2010-01-01", validUntil: "2019-01-01",
                source: "old", supersededBy: "new")
    let new = R(low: nil, high: 116, unit: "mg/dL", sex: "any", validFrom: "2019-01-01", validUntil: nil,
                source: "new", supersededBy: nil)
    let female = R(low: nil, high: 100, unit: "mg/dL", sex: "female", validFrom: "2019-01-01", validUntil: nil,
                   source: "female", supersededBy: nil)
    let ranges = [old, new, female]
    #expect(DoctorLetter.range(ranges, unit: "mg/dl", date: "2026-09-04", sex: "male")?.source == "new")
    #expect(DoctorLetter.range(ranges, unit: "mg/dL", date: "2026-09-04", sex: "female")?.source == "female")
    #expect(DoctorLetter.range(ranges, unit: "mg/dL", date: "2015-05-01", sex: nil)?.source == "old")
    #expect(DoctorLetter.range(ranges, unit: "mmol/L", date: "2026-09-04", sex: nil) == nil)
    #expect(DoctorLetter.range(ranges, unit: "mg/dL", date: "2009-12-31", sex: nil) == nil)
    #expect(DoctorLetter.range(ranges, unit: nil, date: "2026-09-04", sex: nil) == nil)
  }

  @Test func theSpecialistLetterKeepsToTheRisk() throws {
    let store = try Self.store()
    let letter = try store.doctorLetter(.specialist("diabetes"), today: Self.today)
    #expect(letter.riskName == "Type 2 diabetes")
    #expect(!letter.trends.isEmpty && letter.trends.allSatisfy { $0.code.map(letter.markers.contains) == true })
    #expect(Set(letter.trends.compactMap(\.code)) == ["4548-4", "29463-7"])
    #expect(letter.latest.flatMap(\.values).allSatisfy { $0.code.map(letter.markers.contains) == true })
    #expect(letter.vitals.isEmpty && letter.activity.isEmpty)  // no diabetes marker among the watch's
    #expect(letter.links.contains { $0.fromId == "diabetes" && $0.toId == "cardiovascular" })
    #expect(letter.answers.allSatisfy { DoctorLetter.risks(linkId: $0.linkId, protocolId: $0.protocolId).contains("diabetes") })
    #expect(letter.answers.contains { $0.linkId == "exercise" })
    let fitness = try store.doctorLetter(.specialist("fitness"), today: Self.today)
    #expect(fitness.vitals.map(\.code) == ["40443-4"] && fitness.activity.map(\.code) == ["94122-9"])
    #expect(throws: (any Error).self) { try store.doctorLetter(.specialist("cancer"), today: Self.today) }
    let risks = try store.letterRisks()
    #expect(risks.map(\.id).contains("cardiovascular") && (risks.first { $0.id == "bone" }?.values ?? -1) == 0)
  }

  @Test func germanAndEnglish() throws {
    let letter = try Self.store().doctorLetter(.gp, today: Self.today)
    let de = letter.html(language: .de), en = letter.html(language: .en)
    #expect(de.contains("<html lang=\"de\">") && de.contains("Arztbrief für die Hausarztpraxis"))
    #expect(de.contains("Aktuelle Laborwerte") && de.contains("Vitalwerte der Apple Watch") && de.contains("Sport und Aktivität"))
    #expect(de.contains("Anamnese") && de.contains("Fragen an die Ärztin oder den Arzt") && de.contains("Keine Diagnose"))
    #expect(de.contains("04.09.2026: 5,4 %"))
    #expect(en.contains("Doctor's letter for my GP") && en.contains("2026-09-04: 5.4 %") && en.contains("Not a diagnosis"))
    #expect(!de.contains("http") && !de.contains("<script"))  // nothing loaded, nothing run
    let md = letter.markdown(language: .en)
    #expect(md.hasPrefix("# Doctor's letter for my GP") && md.contains("## 2. Latest lab tests"))
    #expect(md.contains("| LDL-Cholesterin | **141 mg/dL ↑** |"))
    let specialist = try Self.store().doctorLetter(.specialist("cardiovascular"), today: Self.today)
    #expect(specialist.html(language: .de).contains("Facharztpraxis: Herz-Kreislauf-Erkrankung"))
    #expect(specialist.markdown(language: .en).contains("Related risks"))
    #expect(DoctorLetter.Language(locale: Locale(identifier: "de_AT")) == .de)
    #expect(DoctorLetter.Language(locale: Locale(identifier: "fr_FR")) == .en)
  }

  /// With DOCTOR_LETTER_DB and DOCTOR_LETTER_OUT set: renders that store's letters (GP and
  /// cardiovascular, German and English) into the folder, to look at.
  @Test func renderLettersForReview() throws {
    let env = ProcessInfo.processInfo.environment
    guard let db = env["DOCTOR_LETTER_DB"], let out = env["DOCTOR_LETTER_OUT"] else { return }
    let store = try HealthStore(path: db, readOnly: true)
    for (name, variant) in [("gp", DoctorLetter.Variant.gp), ("cardiovascular", .specialist("cardiovascular"))] {
      let letter = try store.doctorLetter(variant, today: env["DOCTOR_LETTER_TODAY"])
      for lang in DoctorLetter.Language.allCases {
        try letter.html(language: lang).write(toFile: "\(out)/letter-\(name)-\(lang.rawValue).html", atomically: true, encoding: .utf8)
        try letter.markdown(language: lang).write(toFile: "\(out)/letter-\(name)-\(lang.rawValue).md", atomically: true, encoding: .utf8)
      }
    }
  }
}
