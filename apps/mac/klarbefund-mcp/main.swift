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
let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)
let snapshot = container?.appendingPathComponent("Snapshot/health.rl")
/// Where anamnesis answers wait for Klarbefund for Mac, which owns the graph and stores them.
let inbox = container?.appendingPathComponent("Inbox", isDirectory: true)

let instructions = """
  This server is the user's personal health graph, kept by Klarbefund for Mac on their own Mac \
  (Neo4j Relate, an embedded graph database; one file, read-only here, nothing is stored in a cloud). \
  The one thing it can hand back is the user's own anamnesis answers, through save_anamnesis_answers, \
  which Klarbefund for Mac checks and stores.

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
  so a value leads to its evidence: (o:Observation)-[:CODED_BY]->(:LoincCode)<-[:EXAMINES]-(st:Study). \
  Study.kind is 'study' or 'guideline', Study.topics clusters them; (:Study)-[:CITES]->(:Study) where one source cites another.
  - OMOP research copies: (:OMOPPerson), (:OMOPMeasurement).
  - Anamnesis, when the person answered one: (:Patient)-[:HAS_RESPONSE]->(:QuestionnaireResponse {authored})-[:HAS_ANSWER]->\
  (:Answer {linkId, question, labels, text, riskFactor})-[:RISK_FACTOR_FOR]->(:HealthRisk); (:Answer)-[:BASED_ON]->(:LoincCode). \
  Use the latest answer per linkId (with a.context, the sample date it was asked about), and quote the \
  person's own words in a.text.
  - Anamnesis: call anamnesis_plan and ask only its questions, never what its known and skipped lists \
  already answer; store the answers with save_anamnesis_answers once the person has confirmed them.

  How to work:
  - Call get_schema first, then read_cypher. Count a value seen in two reports once: filter `o.duplicateOf IS NULL`.
  - Compare values with ReferenceRange in the same unit (r.ucum = o.unit) that applied on the value's date \
  (r.validFrom <= o.effectiveDate and (r.validUntil IS NULL or o.effectiveDate < r.validUntil)); say which range and \
  source you used: (r)-[:SOURCED_FROM]->(:Study {citation, url, pubmedUrl}). If r.validUntil is set, say the range was \
  superseded and quote r.supersededBy.
  - When a value raises one risk, follow RAISES_RISK_OF to the risks that one raises in turn, and cite the Study.
  - Name dates and sources (report title, lab) for every number you quote, so the user can check it on the paper.
  - If the graph is empty or unavailable, explain the setup: open Klarbefund for Mac, then on the iPhone open \
  Klarbefund, More (the … button), Export to my Mac (Relate), scan the QR code the Mac shows, and send the reports.
  - This is not medical advice. Help the user understand their data and prepare questions for their doctor.

  Prompts and guides: this server offers \(MCPCatalog.prompts.count) prompts for the common questions \
  (prompts/list: risks, values and trends, the doctor's visit, habits, the evidence, setup and privacy) and \
  \(MCPCatalog.guides.count) guides as resources (resources/list). Start with klarbefund://guide/start; \
  klarbefund://guide/security explains where the data is and what this server can do.

  \(MCPCatalog.rules)
  """

// ── JSON-RPC over stdio ───────────────────────────────────────────────────────
func send(_ object: [String: Any]) {
  guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else { return }
  FileHandle.standardOutput.write(data)
  FileHandle.standardOutput.write(Data("\n".utf8))
}

func result(_ id: Any, _ value: Any) { send(["jsonrpc": "2.0", "id": id, "result": value]) }
func failure(_ id: Any, _ code: Int, _ message: String, data: Any? = nil) {
  var error: [String: Any] = ["code": code, "message": message]
  if let data { error["data"] = data }
  send(["jsonrpc": "2.0", "id": id, "error": error])
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

let readOnly: [String: Any] = ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]

/// Anamnesis answers leave this process only as a request Klarbefund for Mac stores: no graph write here.
let handsOver: [String: Any] = [
  "readOnlyHint": false, "destructiveHint": false, "idempotentHint": false, "openWorldHint": false,
]

func anamnesisPlan() throws -> String {
  let graph = try openGraph()
  let data = try JSONSerialization.data(withJSONObject: try graph.anamnesisPlan(), options: [.sortedKeys])
  return String(decoding: data, as: UTF8.self)
}

func saveAnamnesis(_ answers: [String: Any]) throws -> String {
  guard snapshot.map({ FileManager.default.fileExists(atPath: $0.path) }) == true, let inbox else {
    throw GraphError.closed
  }
  let sent = try AnamnesisInbox.submit(answers, source: "claude", into: inbox)
  return "Handed \(sent.answers) answers to Klarbefund for Mac, which stores them in the health graph within a "
    + "few seconds. Call anamnesis_plan again afterwards: answered questions then appear under skipped."
}

func anamnesisProtocols() throws -> String {
  // What was stored before, newest first; the definitions come with the helper (Protocols, generated).
  let stored = (try? openGraph().rows(cypher: """
    MATCH (:Patient)-[:HAS_RESPONSE]->(r:QuestionnaireResponse)-[:HAS_ANSWER]->(a:Answer)
    WHERE r.protocol IS NOT NULL
    RETURN r.protocol AS protocol, r.authored AS authored, r.score AS score, r.band AS band,
           a.linkId AS linkId, a.codes AS codes, a.text AS text ORDER BY r.authored DESC
    """)) ?? []
  let body: [String: Any] = [
    "protocols": Protocols.catalog(), "stored": stored,
    "prefill": "Each question's prefill says what in the graph can answer it (a LOINC code, Apple Watch weekly "
      + "means, an earlier answer). Read those values with read_cypher, choose the option they fall in, and "
      + "show the person the value, its date and the option, to confirm or change. Never prefill what only "
      + "the person knows.",
  ]
  let data = try JSONSerialization.data(withJSONObject: body, options: [.sortedKeys])
  return String(decoding: data, as: UTF8.self)
}

func saveProtocol(_ id: String, _ answers: [String: Any]) throws -> String {
  guard snapshot.map({ FileManager.default.fileExists(atPath: $0.path) }) == true, let inbox else {
    throw GraphError.closed
  }
  let sent = try AnamnesisInbox.submitProtocol(id, answers, source: "claude", into: inbox)
  return "Handed \(sent.answers) answers of \(id) to Klarbefund for Mac, which scores them and stores them, "
    + "coded with SNOMED CT, within a few seconds."
}

let tools: [[String: Any]] = [
  [
    "name": "get_schema",
    "title": "Health graph schema",
    "description": "Labels and relationship types in the user's health graph, with counts. Call this first.",
    "inputSchema": ["type": "object", "properties": [String: Any]()],
    "annotations": readOnly,
  ],
  [
    "name": "read_cypher",
    "title": "Read-only Cypher query",
    "description": "Run one read-only Cypher query (MATCH ... RETURN) against the user's health graph. Returns JSON rows (at most 500).",
    "inputSchema": [
      "type": "object",
      "properties": [
        "statement": ["type": "string", "description": "The Cypher query."],
        "parameters": ["type": "object", "description": "Query parameters, e.g. {\"loinc\": \"4548-4\"}."],
      ],
      "required": ["statement"],
    ],
    "annotations": readOnly,
  ],
  [
    "name": "anamnesis_plan",
    "title": "Anamnesis from my data",
    "description": "Findings in the user's own data (newest values outside the guideline range valid on their date, "
      + "or at a limit; FIB-4; exercise test; blood oxygen; a score input only the user knows), what the graph "
      + "already answers (known, and questions answered in the last 12 months under skipped), values too old "
      + "to judge (rechecks), and only the questions left, each with its options, the findings that raise it "
      + "and the LOINC codes it is about. Ask these questions; do not ask what known or skipped already answers.",
    "inputSchema": ["type": "object", "properties": [String: Any]()],
    "annotations": readOnly,
  ],
  [
    "name": "save_anamnesis_answers",
    "title": "Store my anamnesis answers",
    "description": "Hands the user's anamnesis answers to Klarbefund for Mac, which checks them and stores them in "
      + "the health graph. Only after the user has seen and confirmed the answers. Keys are the question keys "
      + "from anamnesis_plan (e.g. smoking, exercise-before-sample@2026-01-15); a value is an option code, a "
      + "list of codes where several are allowed, or {\"codes\": [...], \"text\": \"the user's own words\", "
      + "\"basedOn\": [LOINC codes from the plan], \"findings\": [finding ids from the plan]}. A code that is not "
      + "one of the question's options refuses all answers.",
    "inputSchema": [
      "type": "object",
      "properties": ["answers": ["type": "object", "description": "Question key -> answer, as described."]],
      "required": ["answers"],
    ],
    "annotations": handsOver,
  ],
  [
    "name": "anamnesis_protocols",
    "title": "Anamnesis protocols",
    "description": "The validated questionnaires in the graph's own category: Life's Essential 8, FINDRISC, "
      + "AUDIT-C, MEDAS-14, PHQ-2, and structured history (tobacco as the Patient Summary codes it, family "
      + "history read by the ESC 2021 rule, lipid-lowering medication with dates, eating pattern and fasting). "
      + "Each question with its LOINC code, options with points and the SNOMED CT concept each asserts, what "
      + "in the graph can prefill it, the bands, why it matters and a critical note; plus what the user "
      + "stored before.",
    "inputSchema": ["type": "object", "properties": [String: Any]()],
    "annotations": readOnly,
  ],
  [
    "name": "save_protocol_answers",
    "title": "Store my answers to a protocol",
    "description": "Hands one protocol's answers to Klarbefund for Mac, which checks, scores and stores them "
      + "with their SNOMED CT codes. Only after the user has seen and confirmed them, prefilled ones included. "
      + "protocol: an id from anamnesis_protocols (e.g. findrisc). answers: {linkId: option code, a list of "
      + "codes where several are allowed, or {\"codes\": [...], \"text\": \"YYYY-MM for a month, or the user's "
      + "words\", \"prefilled\": \"where a prefilled answer came from\"}}. A code that is not an option refuses "
      + "all answers.",
    "inputSchema": [
      "type": "object",
      "properties": [
        "protocol": ["type": "string", "description": "The protocol id, e.g. findrisc."],
        "answers": ["type": "object", "description": "linkId -> answer, as described."],
      ],
      "required": ["protocol", "answers"],
    ],
    "annotations": handsOver,
  ],
]

// ── the catalog: prompts and guides (MCPCatalog, shared with Klarbefund for Mac) ──
struct RPCError: Error {
  let code: Int, message: String
  var data: Any? = nil
}

let prompts: [[String: Any]] = MCPCatalog.prompts.map { p in
  [
    "name": p.name, "title": p.title, "description": p.description,
    "arguments": p.arguments.map { ["name": $0.name, "description": $0.description, "required": $0.required] },
  ]
}

func getPrompt(_ params: [String: Any]) throws -> [String: Any] {
  let name = params["name"] as? String ?? ""
  guard let p = MCPCatalog.prompts.first(where: { $0.name == name }) else {
    throw RPCError(code: -32602, message: "unknown prompt: \(name)")
  }
  let given = (params["arguments"] as? [String: Any] ?? [:]).compactMapValues { $0 as? String }
  if let missing = p.arguments.first(where: {
    $0.required && (given[$0.name]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "").isEmpty
  }) {
    throw RPCError(code: -32602, message: "missing required argument: \(missing.name)", data: ["argument": missing.name])
  }
  return [
    "description": p.title,
    "messages": [["role": "user", "content": ["type": "text", "text": MCPCatalog.render(p, arguments: given)]]],
  ]
}

let guides = MCPCatalog.guides
let resources: [[String: Any]] = guides.map {
  ["uri": $0.uri, "name": $0.name, "title": $0.title, "description": $0.description, "mimeType": "text/markdown"]
}

func readResource(_ params: [String: Any], modern: Bool) throws -> [String: Any] {
  let uri = params["uri"] as? String ?? ""
  guard let g = guides.first(where: { $0.uri == uri }) else {
    // 2026-07-28 answers an unknown resource with invalid params; older revisions used -32002.
    throw RPCError(code: modern ? -32602 : -32002, message: "Resource not found", data: ["uri": uri])
  }
  return ["contents": [["uri": g.uri, "mimeType": "text/markdown", "text": g.text]]]
}

// ── the protocol ─────────────────────────────────────────────────────────────
// Legacy revisions (2025-11-25 and older) start with initialize. 2026-07-28 is
// stateless: discovery through server/discover, and every request names its
// revision in params._meta. A request without that entry is a legacy request.
let versionKey = "io.modelcontextprotocol/protocolVersion"
let serverInfoKey = "io.modelcontextprotocol/serverInfo"
let supportedVersions = MCPCatalog.modernVersions + MCPCatalog.legacyVersions
let serverInfo: [String: Any] = ["name": MCPCatalog.serverName, "title": MCPCatalog.serverTitle, "version": version]
let capabilities: [String: Any] = [
  "tools": ["listChanged": false], "prompts": ["listChanged": false], "resources": ["listChanged": false],
]

/// A 2026-07-28 result: resultType, the server in _meta, and, for the lists and
/// guides (the same for everyone, changed only by an app update), caching hints.
/// Never for tools/call: its rows are the user's own.
func modern(_ value: [String: Any], cache: Bool = false) -> [String: Any] {
  var out = value
  out["resultType"] = "complete"
  var meta = out["_meta"] as? [String: Any] ?? [:]
  meta[serverInfoKey] = serverInfo
  out["_meta"] = meta
  if cache {
    out["ttlMs"] = 3_600_000
    out["cacheScope"] = "public"
  }
  return out
}

// ── the loop ─────────────────────────────────────────────────────────────────
while let line = readLine(strippingNewline: true) {
  guard !line.isEmpty, let data = line.data(using: .utf8),
    let msg = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
    let method = msg["method"] as? String
  else { continue }
  guard let id = msg["id"] else { continue }  // a notification: nothing to answer
  let params = msg["params"] as? [String: Any] ?? [:]
  let requested = (params["_meta"] as? [String: Any])?[versionKey] as? String
  if let requested, !MCPCatalog.modernVersions.contains(requested) {
    failure(id, -32022, "Unsupported protocol version", data: ["supported": supportedVersions, "requested": requested])
    continue
  }
  let isModern = requested != nil
  /// Answers in the revision the request came in.
  func reply(_ value: [String: Any], cache: Bool = false) {
    result(id, isModern ? modern(value, cache: cache) : value)
  }
  do {
    switch method {
    case "initialize":
      let asked = params["protocolVersion"] as? String ?? ""
      let legacy = MCPCatalog.legacyVersions
      result(id, [
        "protocolVersion": legacy.contains(asked) ? asked : legacy[0],
        "capabilities": capabilities,
        "serverInfo": serverInfo,
        "instructions": instructions,
      ])
    case "server/discover":
      result(id, modern([
        "supportedVersions": supportedVersions,
        "capabilities": capabilities,
        "instructions": instructions,
      ], cache: true))
    case "ping":
      reply([:])
    case "tools/list":
      reply(["tools": tools], cache: true)
    case "tools/call":
      let name = params["name"] as? String ?? ""
      let args = params["arguments"] as? [String: Any] ?? [:]
      switch name {
      case "get_schema":
        do { reply(text(try schema())) } catch { reply(text("\(error)", error: true)) }
      case "read_cypher":
        guard let statement = args["statement"] as? String else {
          reply(text("read_cypher needs a statement", error: true)); break
        }
        do {
          reply(text(try readCypher(statement, args["parameters"] as? [String: Any] ?? [:])))
        } catch {
          reply(text("\(error)", error: true))
        }
      case "anamnesis_plan":
        do { reply(text(try anamnesisPlan())) } catch { reply(text("\(error)", error: true)) }
      case "anamnesis_protocols":
        do { reply(text(try anamnesisProtocols())) } catch { reply(text("\(error)", error: true)) }
      case "save_protocol_answers":
        guard let id = args["protocol"] as? String, let answers = args["answers"] as? [String: Any], !answers.isEmpty
        else { reply(text("save_protocol_answers needs a protocol and answers", error: true)); break }
        do { reply(text(try saveProtocol(id, answers))) } catch { reply(text("\(error)", error: true)) }
      case "save_anamnesis_answers":
        guard let answers = args["answers"] as? [String: Any], !answers.isEmpty else {
          reply(text("save_anamnesis_answers needs answers", error: true)); break
        }
        do { reply(text(try saveAnamnesis(answers))) } catch { reply(text("\(error)", error: true)) }
      default:
        throw RPCError(code: -32602, message: "unknown tool \(name)")
      }
    case "prompts/list":
      reply(["prompts": prompts], cache: true)
    case "prompts/get":
      reply(try getPrompt(params))
    case "resources/list":
      reply(["resources": resources], cache: true)
    case "resources/templates/list":
      reply(["resourceTemplates": [[String: Any]]()], cache: true)
    case "resources/read":
      reply(try readResource(params, modern: isModern), cache: true)
    default:
      failure(id, -32601, "method not found: \(method)")
    }
  } catch let error as RPCError {
    failure(id, error.code, error.message, data: error.data)
  } catch {
    failure(id, -32603, "\(error)")
  }
}
