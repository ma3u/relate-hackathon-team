import AppKit
import Foundation
import HealthGraph
import HealthGraphReceiver

/// Where Klarbefund for Mac keeps things. Everything is inside the app's sandbox,
/// except the read-only snapshot for Claude, which lives in the app-group
/// container that the MCP helper shares, and only while the app is open.
enum Paths {
  static let appGroup = "38R8Z4P7S8.red.mabu.meinbefund"
  static var data: URL {
    FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent("HealthGraph", isDirectory: true)
  }
  static var store: URL { data.appendingPathComponent("health.rl") }
  static var sealed: URL { data.appendingPathComponent("health.rl.sealed") }
  static var identity: URL { data.appendingPathComponent("pairing", isDirectory: true) }
  static var snapshotDir: URL? {
    FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)?
      .appendingPathComponent("Snapshot", isDirectory: true)
  }
  static var snapshot: URL? { snapshotDir?.appendingPathComponent("health.rl") }
  /// Anamnesis answers the MCP helper hands over (AnamnesisInbox); the app stores them.
  static var inbox: URL? {
    FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)?
      .appendingPathComponent("Inbox", isDirectory: true)
  }
}

struct GraphCounts: Equatable {
  var reports = 0, values = 0, weeks = 0, codes = 0, ranges = 0
}

@MainActor
final class AppModel: ObservableObject {
  static let shared = AppModel()

  @Published var link: String?
  @Published var qr: NSImage?
  @Published var address = ""
  @Published var counts = GraphCounts()
  @Published var lastReceived: Date?
  @Published var activity: [String] = []
  @Published var problem: String?
  @Published var claudeMessage: String?

  private var server: ReceiverServer?
  private var refresh: Task<Void, Never>?
  private var inboxTimer: Timer?
  private var started = false

  /// Opens the sealed graph, prepares it, and starts receiving from the paired iPhone.
  func start() {
    guard !started else { return }
    started = true
    do {
      try FileManager.default.createDirectory(at: Paths.data, withIntermediateDirectories: true)
      try Seal.open(sealed: Paths.sealed, into: Paths.store)
      do {  // schema and the knowledge layer, then release the store for the receiver
        let store = try HealthStore(path: Paths.store.path)
        try store.initSchema()
        try store.seedKnowledge()
        try store.seedProtocols()  // the anamnesis protocols' category, questions and SNOMED CT codes
      }
      address = Network.lanAddress()
      let identity = try Identity.ensure(in: Paths.identity, host: address)
      let name = Network.hostName
      let core = ReceiverCore(store: Paths.store, token: identity.token, name: name) { line in
        Task { @MainActor in AppModel.shared.received(line) }
      }
      let server = try ReceiverServer(core: core, identity: identity)
      var bound: Int?
      for candidate in 8787...8797 where bound == nil { bound = try? server.start(port: candidate) }
      let port = try bound ?? server.start(port: 0)
      self.server = server
      let link = Pairing.link(
        url: "https://\(address):\(port)", token: identity.token, fingerprint: identity.fingerprint,
        name: name, store: Paths.store.lastPathComponent)
      self.link = link
      if let png = QRCode(link)?.png(scale: 10, border: 2) { qr = NSImage(data: png) }
      scheduleRefresh(after: 0)
      // Anamnesis answers from Claude: stored by the app, which owns the graph (every 3 s while open).
      inboxTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { _ in
        Task { @MainActor in AppModel.shared.applyInbox() }
      }
    } catch {
      problem = "Klarbefund could not open your health graph: \(error)"
    }
  }

  /// Stores the anamnesis answers waiting in the inbox, then refreshes Claude's snapshot.
  func applyInbox() {
    guard let inbox = Paths.inbox,
      let waiting = try? FileManager.default.contentsOfDirectory(atPath: inbox.path),
      AnamnesisInbox.waiting(waiting)
    else { return }
    do {
      let store = try HealthStore(path: Paths.store.path)
      for line in AnamnesisInbox.apply(from: inbox, to: store) { received(line) }
    } catch {
      NSLog("anamnesis inbox: \(error)")  // the store is busy (a transfer): the next tick tries again
    }
  }

  /// Stops receiving, removes Claude's snapshot and seals the graph.
  func stop() {
    inboxTimer?.invalidate()
    applyInbox()
    server?.stop()
    server = nil
    if let snap = Paths.snapshotDir { try? FileManager.default.removeItem(at: snap) }
    do { try Seal.close(Paths.store, into: Paths.sealed) } catch { NSLog("seal failed: \(error)") }
  }

  func received(_ line: String) {
    activity.insert(line, at: 0)
    if activity.count > 30 { activity.removeLast() }
    lastReceived = Date()
    scheduleRefresh(after: 2)
  }

  /// Copies the graph to Claude's snapshot and recounts it, a moment after the
  /// last write, so the copy is never taken mid-transfer.
  func scheduleRefresh(after seconds: Double) {
    refresh?.cancel()
    refresh = Task.detached(priority: .utility) {
      try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
      guard !Task.isCancelled else { return }
      let counts = Self.snapshotAndCount()
      await MainActor.run { if let counts { AppModel.shared.counts = counts } }
    }
  }

  nonisolated static func snapshotAndCount() -> GraphCounts? {
    guard let dir = Paths.snapshotDir, let snap = Paths.snapshot else { return nil }
    let fm = FileManager.default
    do {
      try fm.createDirectory(at: dir, withIntermediateDirectories: true)
      let tmp = dir.appendingPathComponent("health.rl.new")
      try? fm.removeItem(at: tmp)
      try fm.copyItem(at: Paths.store, to: tmp)
      if fm.fileExists(atPath: snap.path) {
        _ = try fm.replaceItemAt(snap, withItemAt: tmp)
      } else {
        try fm.moveItem(at: tmp, to: snap)
      }
      let g = try HealthStore(path: snap.path, readOnly: true)
      func n(_ cypher: String) -> Int { Int((try? g.rows(cypher: cypher).first?["n"]) ?? "0") ?? 0 }
      return GraphCounts(
        reports: (try? g.count("DiagnosticReport")) ?? 0,
        values: n("MATCH (o:Observation) WHERE o.duplicateOf IS NULL AND coalesce(o.sourceKind, '') <> 'device-weekly-mean' RETURN count(o) AS n"),
        weeks: n("MATCH (o:Observation) WHERE o.sourceKind = 'device-weekly-mean' RETURN count(o) AS n"),
        codes: (try? g.count("LoincCode")) ?? 0,
        ranges: (try? g.count("ReferenceRange")) ?? 0)
    } catch {
      NSLog("snapshot failed: \(error)")
      return nil
    }
  }

  func connectClaude() {
    do {
      try ClaudeConnect.install()
      claudeMessage = "Claude Desktop is asking to install “Klarbefund Health Graph”. Click Install, then start a new chat."
    } catch {
      claudeMessage = "\(error)"
    }
  }
}
