// klarbefund-mcp: the MCP server Claude Desktop starts for Klarbefund for Mac.
//
// It speaks MCP over stdio (JSON-RPC 2.0, one message per line) and answers
// read-only Cypher against a snapshot of the health graph that Klarbefund for
// Mac keeps in the shared app-group container while the app is open. Closing
// the app deletes the snapshot and seals the graph, so Claude can read the
// graph only while the person has Klarbefund open.
import Foundation
import HealthGraph
import Relate

let appGroup = "38R8Z4P7S8.red.mabu.meinbefund"
let version = "1.0.0"
let snapshot = FileManager.default
  .containerURL(forSecurityApplicationGroupIdentifier: appGroup)?
  .appendingPathComponent("Snapshot/health.rl")

let instructions = """
  This server is the user's personal health graph, kept by Klarbefund for Mac on their own Mac \
  (Neo4j Relate, an embedded graph database; one file, read-only here, nothing is stored in a cloud).

  What is in it:
  - (:Patient) the user, with birthYear and gender when they chose to share them.
  - (:Patient)-[:HAS_DIAGNOSTIC_REPORT]->(:DiagnosticReport {title, effectiveDate, performer})-[:HAS_RESULT]->(:Observation)
    lab values scanned from paper reports by Klarbefund on the iPhone.
  - (:Patient)-[:HAS_OBSERVATION]->(:Observation) every value; Apple Watch weekly means have \
  sourceKind = 'device-weekly-mean' and hang on the Patient without a report.
  - Observation properties: code (LOINC), display, valueQuantity, unit, effectiveDate, sourceKind, \
  sourceLine (page and line on the paper), referenceLow/High as printed by the lab, duplicateOf.
  - (:Observation)-[:CODED_BY]->(:LoincCode {code}); (:Observation)-[:SAME_AS]->(:Observation) for a value seen in two reports.
  - Knowledge: (:LoincCode)-[:MARKER_OF {source}]->(:HealthRisk {id, name}); \
  (:RiskScore {name, source})-[:ESTIMATES]->(:HealthRisk), (:RiskScore)-[:USES]->(:LoincCode); \
  (:ReferenceRange {guidelineLow, guidelineHigh, optimalLow, optimalHigh, ucum, sex, summary, sourceLabel, sourceUrl})-[:APPLIES_TO]->(:LoincCode).
  - How risks raise each other: (:HealthRisk)-[:RAISES_RISK_OF {summary, measure, estimate, ciLow, ciHigh, studies}]->(:HealthRisk), \
  from meta-analyses and guidelines; (:Study {citation, title, year, design, url})-[:ABOUT]->(:HealthRisk) for the evidence \
  (k.studies holds the Study ids). Observational: an association, not proof of cause. \
  (:Study {pmid, pubmedUrl})-[:EXAMINES]->(:LoincCode) and -[:INFORMS]->(:RiskScore): the markers and scores a study is about, \
  so a value leads to its evidence: (o:Observation)-[:CODED_BY]->(:LoincCode)<-[:EXAMINES]-(st:Study).
  - OMOP research copies: (:OMOPPerson), (:OMOPMeasurement).

  How to work:
  - Call get_schema first, then read_cypher. Count a value seen in two reports once: filter `o.duplicateOf IS NULL`.
  - Compare values with ReferenceRange in the same unit (r.ucum = o.unit); say which range and source you used.
  - When a value raises one risk, follow RAISES_RISK_OF to the risks that one raises in turn, and cite the Study.
  - Name dates and sources (report title, lab) for every number you quote, so the user can check it on the paper.
  - If the graph is empty or unavailable, explain the setup: open Klarbefund for Mac, then on the iPhone open \
  Klarbefund, Menu, Export to my Mac (Relate), scan the QR code the Mac shows, and send the reports.
  - This is not medical advice. Help the user understand their data and prepare questions for their doctor.
  """

// ── JSON-RPC over stdio ───────────────────────────────────────────────────────
func send(_ object: [String: Any]) {
  guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else { return }
  FileHandle.standardOutput.write(data)
  FileHandle.standardOutput.write(Data("\n".utf8))
}

func result(_ id: Any, _ value: Any) { send(["jsonrpc": "2.0", "id": id, "result": value]) }
func failure(_ id: Any, _ code: Int, _ message: String) {
  send(["jsonrpc": "2.0", "id": id, "error": ["code": code, "message": message]])
}

func text(_ s: String, error: Bool = false) -> [String: Any] {
  ["content": [["type": "text", "text": s]], "isError": error]
}

// ── the graph ────────────────────────────────────────────────────────────────
enum GraphError: Error, CustomStringConvertible {
  case closed, write
  var description: String {
    switch self {
    case .closed:
      return "Klarbefund for Mac is not open, so the health graph is sealed. Ask the user to open "
        + "Klarbefund for Mac (and, if they have not yet, to pair their iPhone and send their reports), then try again."
    case .write:
      return "This server is read-only: use MATCH ... RETURN queries only."
    }
  }
}

func openGraph() throws -> HealthStore {
  guard let snapshot, FileManager.default.fileExists(atPath: snapshot.path) else { throw GraphError.closed }
  return try HealthStore(path: snapshot.path, readOnly: true)
}

let writeClause = try! NSRegularExpression(
  pattern: #"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b"#, options: [.caseInsensitive])

func json(_ v: CypherValue) -> Any {
  switch v {
  case .null: return NSNull()
  case .bool(let b): return b
  case .int(let i): return i
  case .float(let d): return d.isFinite ? d : String(d)
  case .string(let s): return s
  case .list(let items): return items.map(json)
  case .map(let m): return m.mapValues(json)
  default: return v.plain
  }
}

func readCypher(_ statement: String, _ parameters: [String: Any]) throws -> String {
  let range = NSRange(statement.startIndex..., in: statement)
  if writeClause.firstMatch(in: statement, range: range) != nil { throw GraphError.write }
  let graph = try openGraph()
  let res = try graph.connection.query(statement, parameters.mapValues(JSON.cypher))
  let rows = res.rows.prefix(500).map { row in
    Dictionary(uniqueKeysWithValues: zip(res.columns, row.map(json)))
  }
  var out: [String: Any] = ["columns": res.columns, "rows": rows]
  if res.rows.count > 500 { out["note"] = "first 500 of \(res.rows.count) rows; narrow the query" }
  let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
  return String(decoding: data, as: UTF8.self)
}

func schema() throws -> String {
  let graph = try openGraph()
  let labels = try graph.rows(cypher: "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC")
  let rels = try graph.rows(cypher: "MATCH (a)-[r]->(b) RETURN labels(a)[0] AS from, type(r) AS type, labels(b)[0] AS to, count(*) AS n ORDER BY n DESC")
  var lines = ["Health graph (read-only snapshot, Klarbefund for Mac)", "", "Node labels:"]
  lines += labels.map { "- \($0["label"] ?? ""): \($0["n"] ?? "")" }
  lines += ["", "Relationships:"]
  lines += rels.map { "- (:\($0["from"] ?? ""))-[:\($0["type"] ?? "")]->(:\($0["to"] ?? "")): \($0["n"] ?? "")" }
  return lines.joined(separator: "\n")
}

let tools: [[String: Any]] = [
  [
    "name": "get_schema",
    "description": "Labels and relationship types in the user's health graph, with counts. Call this first.",
    "inputSchema": ["type": "object", "properties": [String: Any]()],
  ],
  [
    "name": "read_cypher",
    "description": "Run one read-only Cypher query (MATCH ... RETURN) against the user's health graph. Returns JSON rows (at most 500).",
    "inputSchema": [
      "type": "object",
      "properties": [
        "statement": ["type": "string", "description": "The Cypher query."],
        "parameters": ["type": "object", "description": "Query parameters, e.g. {\"loinc\": \"4548-4\"}."],
      ],
      "required": ["statement"],
    ],
  ],
]

let prompts: [(name: String, title: String, text: String)] = [
  ("whats_in_my_graph", "What is in my health graph?",
   "Using my Klarbefund health graph: what is in it? Count the kinds of data, the sources and the time span, and suggest three questions I could ask next."),
  ("out_of_range", "Which values need attention?",
   "Which of my latest lab values are outside the official guideline range, and which are inside it but not optimal? Use the ReferenceRange nodes, name the health risk each value is a marker of, and the source."),
  ("doctor_visit", "Prepare my doctor's visit",
   "Prepare my next doctor's visit from my health graph: the four most important topics for a six-minute appointment, the trends behind each (with dates), one question per topic, and the guideline sources. Not medical advice."),
]

// ── the loop ─────────────────────────────────────────────────────────────────
while let line = readLine(strippingNewline: true) {
  guard !line.isEmpty, let data = line.data(using: .utf8),
    let msg = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
    let method = msg["method"] as? String
  else { continue }
  guard let id = msg["id"] else { continue }  // a notification: nothing to answer
  let params = msg["params"] as? [String: Any] ?? [:]
  switch method {
  case "initialize":
    let asked = params["protocolVersion"] as? String
    let known = ["2025-06-18", "2025-03-26", "2024-11-05"]
    result(id, [
      "protocolVersion": known.contains(asked ?? "") ? asked! : known[0],
      "capabilities": ["tools": [String: Any](), "prompts": [String: Any]()],
      "serverInfo": ["name": "klarbefund-health", "title": "Klarbefund Health Graph", "version": version],
      "instructions": instructions,
    ])
  case "ping":
    result(id, [String: Any]())
  case "tools/list":
    result(id, ["tools": tools])
  case "tools/call":
    let name = params["name"] as? String ?? ""
    let args = params["arguments"] as? [String: Any] ?? [:]
    do {
      switch name {
      case "get_schema": result(id, text(try schema()))
      case "read_cypher":
        guard let statement = args["statement"] as? String else {
          result(id, text("read_cypher needs a statement", error: true)); continue
        }
        result(id, text(try readCypher(statement, args["parameters"] as? [String: Any] ?? [:])))
      default: failure(id, -32602, "unknown tool \(name)")
      }
    } catch {
      result(id, text("\(error)", error: true))
    }
  case "prompts/list":
    result(id, ["prompts": prompts.map { ["name": $0.name, "title": $0.title, "description": $0.title] }])
  case "prompts/get":
    if let p = prompts.first(where: { $0.name == params["name"] as? String }) {
      result(id, ["description": p.title, "messages": [["role": "user", "content": ["type": "text", "text": p.text]]]])
    } else {
      failure(id, -32602, "unknown prompt")
    }
  default:
    failure(id, -32601, "method not found: \(method)")
  }
}
