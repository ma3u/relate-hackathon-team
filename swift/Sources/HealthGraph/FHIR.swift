import CryptoKit
import Foundation
import Relate

/// Klarbefund FHIR R4 Bundles -> flat graph rows. Pure functions, no database.
/// Port of `health_graph/fhir.py`; the keys follow the EHDS Hub's contract
/// (`storeReportRows`, `app-wearables.ts`) so a later push merges cleanly.
public enum FHIR {
  public static let loinc = "http://loinc.org"
  public static let ucum = "http://unitsofmeasure.org"
  public static let ncbiTaxon = "http://www.ncbi.nlm.nih.gov/taxonomy"
  public static let ext = "https://ehds.mabu.red/fhir/StructureDefinition/epa-ingest-"
  public static let dataAbsent = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
  public static let rendered = "http://hl7.org/fhir/StructureDefinition/rendered-value"
  static let observationCategory = "http://terminology.hl7.org/CodeSystem/observation-category"

  /// Read a Bundle; also accepts Klarbefund's golden-fixture wrapper {"bundle": ...}.
  public static func loadBundle(_ data: Data) throws -> JSONObject {
    let top = try JSON.object(data)
    let bundle = top.object("bundle") ?? top
    guard bundle.string("resourceType") == "Bundle" else {
      throw HealthGraphError.invalid("not a FHIR Bundle")
    }
    return bundle
  }

  static func ext(_ resource: JSONObject, _ name: String) -> Any? {
    for x in resource.objects("extension") where x.string("url") == ext + name {
      if let key = x.keys.sorted().first(where: { $0.hasPrefix("value") }) { return x[key] }
    }
    return nil
  }

  static func coding(_ concept: JSONObject?, _ system: String) -> JSONObject? {
    concept?.objects("coding").first { $0.string("system") == system && $0.text("code") != nil }
  }

  static func unmappedReason(_ code: JSONObject) -> String? {
    for x in code.objects("extension") where x.string("url") == dataAbsent {
      for r in x.object("_valueCode")?.objects("extension") ?? [] where r.string("url") == rendered {
        return r.string("valueString")
      }
      return x.string("valueCode")
    }
    return nil
  }

  static func reportId(_ bundle: JSONObject, _ report: JSONObject) -> String {
    if let id = bundle.object("identifier")?.text("value") { return id }
    // Stable fallback, identical to the Python one: same content -> same id.
    let basis = JSON.pythonDumps([
      report["effectiveDateTime"] ?? NSNull(), report["presentedForm"] ?? NSNull(),
      report["performer"] ?? NSNull(),
    ])
    let hash = SHA256.hash(data: Data(basis.utf8)).map { String(format: "%02x", $0) }.joined()
    return "rpt-" + hash.prefix(12)
  }

  public static func parseBundle(_ bundle: JSONObject, reportId given: String? = nil) throws
    -> ParsedReport
  {
    var byType: [String: [JSONObject]] = [:]
    for entry in bundle.objects("entry") {
      guard let r = entry.object("resource"), let type = r.string("resourceType") else { continue }
      byType[type, default: []].append(r)
    }
    let patients = byType["Patient"] ?? []
    guard patients.count == 1, let patientId = patients[0].string("id") else {
      throw HealthGraphError.invalid("expected exactly one Patient in the bundle")
    }

    let dr = byType["DiagnosticReport"]?.first ?? [:]
    let rid = nonEmpty(given) ?? reportId(bundle, dr)
    let prefix = "\(patientId)-\(rid)"
    let patient = patientAttributes(patients[0])
    let performer = dr.objects("performer").lazy.compactMap { $0.text("display") }.first

    let report: Row = [
      "resourceId": .string(prefix),
      "reportId": .string(rid),
      "fhirId": JSON.cypher(dr["id"]),
      "status": JSON.cypher(dr["status"]),
      "code": JSON.cypher(coding(dr.object("code"), loinc)?["code"]),
      "title": JSON.cypher(dr.object("code")?["text"]),
      "effectiveDate": JSON.cypher(dr["effectiveDateTime"]),
      "issued": JSON.cypher(dr["issued"]),
      "performer": JSON.cypher(performer),
    ]

    var document: Row?
    if let doc = byType["DocumentReference"]?.first {
      let att = doc.objects("content").first?.object("attachment") ?? [:]
      document = [
        "resourceId": .string("\(prefix)-doc"),
        "fhirId": JSON.cypher(doc["id"]),
        "title": JSON.cypher(att.text("title") ?? doc.string("description")),
        "created": JSON.cypher(att["creation"]),
      ]
    }

    var provenance: Row?
    if let prov = byType["Provenance"]?.first {
      provenance = [
        "resourceId": .string("\(prefix)-prov"),
        "recorded": JSON.cypher(prov["recorded"]),
        "activity": JSON.cypher(prov.object("activity")?["text"]),
        "agent": JSON.cypher(prov.objects("agent").first?.object("who")?["display"]),
      ]
    }

    var observations: [Row] = []
    for (offset, o) in (byType["Observation"] ?? []).enumerated() {
      let code = o.object("code") ?? [:]
      let lc = coding(code, loinc)
      let q = o.object("valueQuantity") ?? [:]
      let range = o.objects("referenceRange").first ?? [:]
      let category = coding(o.objects("category").first, observationCategory)
      var taxon: JSONObject?
      for comp in o.objects("component") {
        taxon = coding(comp.object("valueCodeableConcept"), ncbiTaxon) ?? taxon
      }
      let value = JSON.number(q["value"])
      let unit = q.text("code") ?? q.text("unit")
      let ucum = q["system"] == nil || q["system"] is NSNull || q.string("system") == FHIR.ucum
      let status = o.string("status")
      let effective = o.text("effectiveDateTime")
      var row: Row = [
        // Hub contract (storeReportRows): resourceId = patient-report-index
        "resourceId": .string("\(prefix)-\(offset + 1)"),
        "fhirId": JSON.cypher(o["id"]),
        "code": JSON.cypher(lc?["code"]),
        "loincDisplay": JSON.cypher(lc?["display"]),
        "display": .string(code.text("text") ?? lc?.text("display") ?? "Unknown"),
        "valueQuantity": value ?? JSON.cypher(q["value"]),
        "comparator": JSON.cypher(q["comparator"]),
        "unit": JSON.cypher(unit),
        "ucum": .bool(ucum),
        "referenceLow": JSON.cypher(range.object("low")?["value"]),
        "referenceHigh": JSON.cypher(range.object("high")?["value"]),
        "referenceText": JSON.cypher(range["text"]),
        "effectiveDate": JSON.cypher(o["effectiveDateTime"]),
        "category": .string(category?.string("code") ?? "laboratory"),
        "status": JSON.cypher(status),
        "sourceKind": JSON.cypher(ext(o, "source-kind")),
        "sourceLine": JSON.cypher(ext(o, "source-line")),
        "ocrConfidence": JSON.cypher(ext(o, "ocr-confidence")),
        "verifiedByPatientAt": JSON.cypher(ext(o, "verified-by-patient")),
        "originalReading": JSON.cypher(ext(o, "original-reading")),
        "unmappedReason": lc == nil ? JSON.cypher(unmappedReason(code)) : .null,
        "performer": JSON.cypher(performer),
        "taxonCode": JSON.cypher(taxon?["code"]),
        "taxonDisplay": JSON.cypher(taxon?["display"]),
      ]
      // Same acceptance rules as POST /api/patient/app/record on the Hub.
      row["hubEligible"] = .bool(
        status == "preliminary" && lc?.text("code") != nil && value != nil && unit != nil && ucum
          && effective != nil)
      observations.append(row)
    }
    return ParsedReport(
      patientId: patientId, reportId: rid, report: report, document: document,
      provenance: provenance, observations: collapseRepeats(observations), patient: patient)
  }

  /// Year of birth and sex, when the bundle carries them (Klarbefund sends them
  /// only to the person's own Mac, and only when they switch it on). A full date
  /// is cut to its year here: the day is not needed and is not stored.
  /// Same rule as `patient_attributes` in health_graph/fhir.py.
  public static func patientAttributes(_ patient: JSONObject) -> Row {
    var attrs: Row = [:]
    if let date = patient.string("birthDate"), let year = Int(date.prefix(4)), (1900...2100).contains(year) {
      attrs["birthYear"] = .int(Int64(year))
    }
    if let gender = patient.string("gender"), ["male", "female", "other", "unknown"].contains(gender) {
      attrs["gender"] = .string(gender)
    }
    return attrs
  }

  /// One value printed twice on the same report is one measurement.
  ///
  /// Microbiome reports list a species in an overview table and again in a
  /// detail section; read line by line, each copy became its own value and was
  /// counted twice (Nov 12, 2026: 13 extra rows in one report). The first copy
  /// stays, with `repeatedOnReport` saying how often it was printed. Only
  /// numeric values are folded: two text results with one label may well differ.
  /// Same rule as `collapse_repeats` in health_graph/fhir.py.
  public static func collapseRepeats(_ rows: [Row]) -> [Row] {
    var kept: [Row] = []
    var seen: [String: Int] = [:]  // key -> index in kept
    for row in rows {
      switch row["valueQuantity"] {
      case .int?, .float?: fold(row, into: &kept, seen: &seen)
      default: kept.append(row)
      }
    }
    return kept
  }

  private static func fold(_ row: Row, into kept: inout [Row], seen: inout [String: Int]) {
    let key = ["display", "code", "taxonCode", "valueQuantity", "comparator", "unit", "effectiveDate"]
      .map { String(describing: row[$0] ?? .null) }.joined(separator: "\u{1F}")
    if let index = seen[key] {
      let times = kept[index]["repeatedOnReport"]?.intValue ?? 1
      kept[index]["repeatedOnReport"] = .int(times + 1)
    } else {
      seen[key] = kept.count
      kept.append(row)
    }
  }

  // MARK: Apple Health weekly means (Klarbefund WearableFHIR.swift)

  public static let wearableSourceReport = "apple-health-weekly"
  public static let wearableSourceKind = "device-weekly-mean"

  /// LOINC -> UCUM unit and the plausible range, as Klarbefund's WearableFHIR codes them.
  public static let wearableMetrics: [String: (unit: String, min: Double, max: Double)] = [
    "40443-4": ("/min", 20, 250),  // resting heart rate
    "80404-7": ("ms", 1, 500),  // HRV SDNN
    "41950-7": ("/d", 0, 200_000),  // steps per day
    "29463-7": ("kg", 2, 500),  // body weight
    "55411-3": ("min/d", 0, 1440),  // exercise minutes per day
    "94122-9": ("mL/min/kg", 5, 95),  // VO2 max (Apple Watch cardio fitness estimate)
    "9279-1": ("/min", 3, 70),  // respiratory rate
    "59408-5": ("%", 50, 100),  // blood oxygen (SpO2)
    "41981-2": ("kcal/d", 0, 15000),  // active energy per day
    "41982-0": ("%", 1, 75),  // body fat
    "93832-4": ("h/d", 0, 24),  // sleep, all stages
    "93831-6": ("min/d", 0, 1440),  // deep sleep
    "93829-0": ("min/d", 0, 1440),  // REM sleep
    "93830-8": ("min/d", 0, 1440),  // light (Apple: core) sleep
  ]

  /// Weekly-mean Observations -> rows and refusals. The bundle carries no Patient.
  public static func parseWearables(_ bundle: JSONObject, patientId: String) -> (
    rows: [Row], skipped: [Skipped]
  ) {
    var rows: [Row] = []
    var skipped: [Skipped] = []
    var seen: Set<String> = []
    for (offset, entry) in bundle.objects("entry").enumerated() {
      let o = entry.object("resource") ?? [:]
      guard o.string("resourceType") == "Observation" else { continue }
      let rid = o.text("id") ?? "#\(offset + 1)"
      func refuse(_ reason: String) { skipped.append(Skipped(id: rid, reason: reason)) }

      guard o.string("status") == "final" else {
        refuse("a device value is sent as final"); continue
      }
      let lc = coding(o.object("code"), loinc)
      guard let code = lc?.string("code"), let metric = wearableMetrics[code] else {
        refuse("not a device metric Klarbefund sends"); continue
      }
      let q = o.object("valueQuantity") ?? [:]
      guard let value = JSON.number(q["value"]), q.string("system") == ucum,
        q.string("code") == metric.unit
      else {
        refuse("a number in \(metric.unit) (UCUM) is required"); continue
      }
      let v = value.doubleValue ?? 0
      guard metric.min <= v, v <= metric.max else {
        refuse("the value is not plausible"); continue
      }
      let period = o.object("effectivePeriod") ?? [:]
      guard let start = period.text("start"), let end = period.text("end"), end >= start else {
        refuse("a week (effectivePeriod start and end) is required"); continue
      }
      let key = "\(code)-\(start.prefix(10))"
      guard seen.insert(key).inserted else {
        refuse("the same metric and week twice"); continue
      }
      let category = coding(o.objects("category").first, observationCategory)
      rows.append([
        "resourceId": .string("\(patientId)-wear-\(key)"),
        "fhirId": JSON.cypher(o["id"]),
        "code": .string(code),
        "loincDisplay": JSON.cypher(lc?["display"]),
        "display": JSON.cypher(o.object("code")?.text("text") ?? lc?.string("display")),
        "valueQuantity": value,
        "unit": .string(metric.unit),
        "effectiveStart": .string(start),
        "effectiveDate": .string(end),
        "category": .string(category?.string("code") ?? "vital-signs"),
        "status": "final",
        "sourceKind": .string(wearableSourceKind),
        "performer": JSON.cypher(o.object("device")?["display"]),
        "note": JSON.cypher(o.objects("note").first?["text"]),
        "hubEligible": true,
      ])
    }
    return (rows, skipped)
  }
}

public struct ParsedReport: Sendable {
  public let patientId: String
  /// Bare id, as the Hub stores it in Observation.sourceReport.
  public let reportId: String
  public let report: Row
  public let document: Row?
  public let provenance: Row?
  public let observations: [Row]
  /// What the person chose to send about themselves: `birthYear` (year only,
  /// never the day) and `gender`. Empty unless Klarbefund's opt-in switch is on.
  public var patient: Row = [:]

  /// Values the graph keeps without a LOINC code, and why.
  public var unmapped: [Skipped] {
    observations.filter { $0["code"] == .null }.map {
      Skipped(
        id: $0["fhirId"]?.stringValue, reason: $0["unmappedReason"]?.stringValue ?? "no LOINC code")
    }
  }

  public var hubReady: Int { observations.filter { $0["hubEligible"] == .bool(true) }.count }
}

public struct Skipped: Sendable, Equatable {
  public let id: String?
  public let reason: String
  public var json: [String: Any] { ["id": id ?? NSNull(), "reason": reason] }
}
