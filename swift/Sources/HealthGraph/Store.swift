import Foundation
import Relate

/// The local health graph: one Relate store (.rl file). Port of `health_graph/store.py`.
///
/// Relate allows one open handle per store per process; the store closes when
/// this object is released. Open it for one job (an import, a query) and let
/// it go, so other processes (the CLI, `relate serve --mcp`) can open it too.
public final class HealthStore {
  public let connection: Connection
  private let database: Database

  /// Opens (and creates) a store for writing; `readOnly` never creates one.
  public init(path: String, readOnly: Bool = false) throws {
    database = readOnly ? try Database(readOnlyPath: path) : try Database(path: path)
    connection = try database.connect()
  }

  /// Split a .cypher script into statements (on `;`), dropping `//` comment lines.
  public static func statements(_ script: String) -> [String] {
    let text = script.split(separator: "\n", omittingEmptySubsequences: false)
      .filter { !$0.drop(while: { $0 == " " || $0 == "\t" }).hasPrefix("//") }
      .joined(separator: "\n")
    return text.split(separator: ";", omittingEmptySubsequences: false)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
  }

  /// Constraints, indexes and full-text indexes. Idempotent.
  public func initSchema() throws {
    for statement in Self.statements(Cypher.schema) { _ = try connection.query(statement) }
  }

  /// Stores one report. A report sent again replaces its earlier values (the
  /// Hub's storeReportRows rule), so imports are idempotent. Returns the values stored.
  @discardableResult
  public func importReport(_ parsed: ParsedReport) throws -> Int {
    try connection.transaction { c in
      _ = try c.query(Cypher.deleteReport, ["reportId": .string(parsed.reportId)])
      _ = try c.query(
        Cypher.upsertReport,
        [
          "patientId": .string(parsed.patientId),
          "report": .map(parsed.report),
          "document": parsed.document.map(CypherValue.map) ?? .null,
          "provenance": parsed.provenance.map(CypherValue.map) ?? .null,
        ])
      let stored = try c.query(
        Cypher.upsertObservations,
        [
          "patientId": .string(parsed.patientId),
          "reportId": .string(parsed.reportId),
          "reportResourceId": parsed.report["resourceId"] ?? .null,
          "rows": .list(parsed.observations.map(CypherValue.map)),
        ])
      _ = try c.query(Cypher.unlinkSameMeasurements)
      _ = try c.query(Cypher.linkSameMeasurements)
      return Int(stored.records.first?["stored"]?.intValue ?? 0)
    }
  }

  /// Marks a value found in more than one report as one measurement (see
  /// LINK_SAME_MEASUREMENTS in health_graph/store.py). `importReport` runs it;
  /// call it after deleting a report directly. Returns how many copies there are.
  @discardableResult
  public func linkSameMeasurements() throws -> Int {
    _ = try connection.query(Cypher.unlinkSameMeasurements)
    let linked = try connection.query(Cypher.linkSameMeasurements)
    return Int(linked.records.first?["duplicates"]?.intValue ?? 0)
  }

  /// Replaces the patient's Apple Health weekly means (same rule as the Hub).
  @discardableResult
  public func importWearables(patientId: String, rows: [Row]) throws -> Int {
    try connection.transaction { c in
      let params: [String: CypherValue] = [
        "patientId": .string(patientId), "source": .string(FHIR.wearableSourceReport),
      ]
      _ = try c.query(Cypher.replaceWearables, params)
      guard !rows.isEmpty else { return 0 }
      var upsert = params
      upsert["rows"] = .list(rows.map(CypherValue.map))
      let stored = try c.query(Cypher.upsertWearables, upsert)
      return Int(stored.records.first?["stored"]?.intValue ?? 0)
    }
  }

  /// The one patient in this store, else `fallback` (Apple Health bundles carry no Patient).
  public func singlePatient(fallback: String = "meinbefund-local") throws -> String {
    let ids = try connection.query("MATCH (p:Patient) RETURN p.id AS id").records
      .compactMap { $0["id"]?.stringValue }
    return ids.count == 1 ? ids[0] : fallback
  }

  /// The local FHIR -> OMOP CDM v5.4 transform (idempotent). Returns its counts.
  @discardableResult
  public func omopTransform() throws -> [String: Int] {
    var counts: [String: Int] = [:]
    for statement in Self.statements(Cypher.omop) {
      for (key, value) in try connection.query(statement).records.first ?? [:] {
        counts[key] = Int(value.intValue ?? 0)
      }
    }
    return counts
  }

  /// Runs one of `Queries.all` and returns its rows.
  public func run(_ name: String, _ parameters: [String: CypherValue] = [:]) throws
    -> [[String: CypherValue]]
  {
    guard let query = Queries.all[name] else {
      throw HealthGraphError.invalid("unknown query \(name)")
    }
    return try connection.query(query.cypher, parameters).records
  }

  /// Rows as plain text (strings unquoted, null empty), for app screens and
  /// tables: a named query (`Queries.all`) or, with `cypher:`, any read query.
  public func rows(query name: String, _ parameters: [String: String] = [:]) throws
    -> [[String: String]]
  {
    try run(name, parameters.mapValues(CypherValue.string)).map { $0.mapValues(\.plain) }
  }

  public func rows(cypher: String, _ parameters: [String: String] = [:]) throws -> [[String: String]] {
    try connection.query(cypher, parameters.mapValues(CypherValue.string)).records
      .map { $0.mapValues(\.plain) }
  }

  /// Node count for one label (labels are fixed identifiers, never user input).
  public func count(_ label: String) throws -> Int {
    Int(try connection.query("MATCH (n:\(label)) RETURN count(n) AS n").scalar().intValue ?? 0)
  }

  // MARK: One-call imports (receiver, CLI, app)

  /// Parse, store and map one report bundle to OMOP.
  public func receiveReport(_ bundle: JSONObject, reportId: String? = nil) throws -> (
    stored: Int, parsed: ParsedReport
  ) {
    let parsed = try FHIR.parseBundle(bundle, reportId: reportId)
    let stored = try importReport(parsed)
    try omopTransform()
    return (stored, parsed)
  }

  /// Parse, store and map one Apple Health weekly bundle to OMOP.
  public func receiveWearables(_ bundle: JSONObject) throws -> (stored: Int, skipped: [Skipped]) {
    let patient = try singlePatient()
    let (rows, skipped) = FHIR.parseWearables(bundle, patientId: patient)
    let stored = try importWearables(patientId: patient, rows: rows)
    try omopTransform()
    return (stored, skipped)
  }
}

extension CypherValue {
  /// Plain text for tables: strings unquoted, null empty.
  public var plain: String {
    switch self {
    case .null: ""
    case .string(let s): s
    case .int(let i): String(i)
    case .float(let d): String(d)
    case .bool(let b): b ? "true" : "false"
    case .list(let items): "[" + items.map(\.plain).joined(separator: ", ") + "]"
    default: String(describing: self)
    }
  }
}
