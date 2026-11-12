import ArgumentParser
import Foundation
import HealthGraph
import HealthGraphReceiver
import Relate

@main
struct HealthGraphCLI: ParsableCommand {
  static let configuration = CommandConfiguration(
    commandName: "health-graph",
    abstract: "Sovereign Health Graph: Klarbefund FHIR bundles in a local Relate graph.",
    discussion: """
      health-graph import --db health.rl fixtures/fhir/*.json
      health-graph query --db health.rl trend --param loinc=4548-4
      health-graph receive --db ~/RelateHealth/health.rl --require-mount
      """,
    subcommands: [Import.self, Query.self, List.self, Receive.self])
}

struct Import: ParsableCommand {
  static let configuration = CommandConfiguration(abstract: "Import FHIR Bundles into a local .rl store.")
  @Option(help: "The Relate store (.rl).") var db: String
  @Argument(help: "FHIR Bundle JSON files.") var bundles: [String]

  func run() throws {
    let store = try HealthStore(path: db)
    try store.initSchema()
    for path in bundles {
      let parsed = try FHIR.parseBundle(FHIR.loadBundle(Data(contentsOf: URL(fileURLWithPath: path))))
      let stored = try store.importReport(parsed)
      print("\(path): report \(parsed.reportId), \(stored) values (\(parsed.hubReady) Hub-ready)")
    }
    let counts = try store.omopTransform()
    print("OMOP:", counts.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: ", "))
  }
}

struct Query: ParsableCommand {
  static let configuration = CommandConfiguration(abstract: "Run a named read-only query.")
  @Option(help: "The Relate store (.rl).") var db: String
  @Argument(help: "Query name (see `health-graph list`).") var name: String
  @Option(name: .customLong("param"), help: "KEY=VALUE, repeatable.") var params: [String] = []

  func run() throws {
    guard let query = Queries.all[name] else {
      throw ValidationError("unknown query \(name); see `health-graph list`")
    }
    var parameters: [String: CypherValue] = [:]
    for p in params {
      let kv = p.split(separator: "=", maxSplits: 1).map(String.init)
      guard kv.count == 2 else { throw ValidationError("--param needs KEY=VALUE") }
      parameters[kv[0]] = .string(kv[1])
    }
    let result = try HealthStore(path: db, readOnly: true).connection.query(query.cypher, parameters)
    print(table(columns: result.columns, rows: result.rows.map { $0.map(\.plain) }))
  }
}

struct List: ParsableCommand {
  static let configuration = CommandConfiguration(abstract: "List the named queries.")
  func run() {
    for (name, q) in Queries.all.sorted(by: { $0.key < $1.key }) {
      print(name.padding(toLength: 11, withPad: " ", startingAt: 0), q.description)
    }
  }
}

struct Receive: ParsableCommand {
  static let configuration = CommandConfiguration(
    abstract: "Receive reports and Apple Health from Klarbefund (QR pairing).",
    discussion: """
      HTTPS with a self-signed certificate whose SHA-256 the QR code carries (the app
      pins it), a 256-bit bearer token, private-network clients only, one writer at a time.
      The certificate, key and token live in ~/.config/relate-health-graph (0600), shared
      with the Python receiver, so a paired phone keeps working.
      """)
  @Option(help: "The Relate store (.rl).") var db: String
  @Option(help: "Port.") var port = 8787
  @Option(help: "Address to put in the QR code (default: this Mac's Wi-Fi address).") var host: String?
  @Flag(help: "New token: phones paired before must scan again.") var rotate = false
  @Option(help: "Also save the QR code as a PNG (contains the token).") var qrPng: String?
  @Flag(help: "Also print the pairing link (contains the token).") var printLink = false
  @Flag(help: "Refuse to start unless the store's folder is a mounted volume (encrypted vault).")
  var requireMount = false

  func run() throws {
    let store = URL(fileURLWithPath: (db as NSString).expandingTildeInPath).standardizedFileURL
    if requireMount && !Network.isMountPoint(store.deletingLastPathComponent()) {
      // The encrypted volume is not open: writing here would create a new,
      // unencrypted store in the empty mount-point folder.
      throw ValidationError(
        "\(store.deletingLastPathComponent().path) is not a mounted volume; open the encrypted vault first (scripts/health_vault.sh mount)")
    }
    do {  // create the store and schema up front, then release it
      try HealthStore(path: store.path).initSchema()
    }
    let address = host ?? Network.lanAddress()
    let identity = try Identity.ensure(rotate: rotate, host: address)
    let name = Network.hostName
    let url = "https://\(address):\(port)"
    let link = Pairing.link(
      url: url, token: identity.token, fingerprint: identity.fingerprint, name: name,
      store: store.lastPathComponent)

    let core = ReceiverCore(store: store, token: identity.token, name: name) { line in
      print(line)
      fflush(stdout)
    }
    let server = try ReceiverServer(core: core, identity: identity)
    try server.start(port: port)

    print("\nScan this in Klarbefund: Menu -> Export to my Mac (Relate)\n")
    if let qr = QRCode(link) {
      print(qr.terminal(), terminator: "")
      if let qrPng, let png = qr.png() {
        FileManager.default.createFile(atPath: qrPng, contents: png, attributes: [.posixPermissions: 0o600])
        print("QR code also saved to \(qrPng) (it contains the token, keep it private)")
      }
    }
    if printLink { print("\nPairing link (for the Simulator or a paste; it contains the token):\n\(link)") }
    print("\nReceiving at \(url) into \(store.path)")
    print("Certificate SHA-256: \(identity.fingerprint)")
    print("Ctrl+C stops the receiver.\n")
    fflush(stdout)
    try server.wait()
  }
}

func table(columns: [String], rows: [[String]]) -> String {
  guard !rows.isEmpty else { return "(no rows)" }
  let widths = columns.indices.map { i in max(columns[i].count, rows.map { $0[i].count }.max() ?? 0) }
  let line = "+" + widths.map { String(repeating: "-", count: $0 + 2) }.joined(separator: "+") + "+"
  func format(_ values: [String]) -> String {
    "| " + zip(values, widths).map { $0.padding(toLength: $1, withPad: " ", startingAt: 0) }
      .joined(separator: " | ") + " |"
  }
  return ([line, format(columns), line] + rows.map(format) + [line]).joined(separator: "\n")
}
