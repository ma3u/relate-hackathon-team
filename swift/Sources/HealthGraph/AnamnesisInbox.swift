import Foundation

/// How anamnesis answers reach a graph that only its app may write.
///
/// The MCP helper opens the graph read-only (a snapshot), so it cannot store
/// answers itself. It checks them (`Anamnesis.validate`) and leaves one request
/// file in a folder both share (the app-group container's `Inbox`); the app,
/// which owns the graph, stores each request and deletes it, or renames it to
/// `.rejected` with the reason when the graph refuses it. Nothing else is in a
/// request: the answers, where they came from, and when.
public enum AnamnesisInbox {
  public static let suffix = ".anamnesis.json"
  /// One anamnesis protocol's answers (Protocols): from Claude, or from the 3D view's server.
  public static let protocolSuffix = ".protocol.json"

  /// Whether a folder listing holds a request the app should store.
  public static func waiting(_ names: [String]) -> Bool {
    names.contains { $0.hasSuffix(suffix) || $0.hasSuffix(protocolSuffix) }
  }

  /// Checks the answers and writes one request into `directory`. Returns the file and the answer count.
  @discardableResult
  public static func submit(_ answers: JSONObject, source: String, into directory: URL, now: Date = Date())
    throws -> (file: URL, answers: Int)
  {
    let checked = try Anamnesis.validate(answers)
    guard checked.count > 0 else { throw HealthGraphError.invalid("no answers to store") }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let authored = ISO8601DateFormatter().string(from: now)
    let request: JSONObject = ["answers": answers, "source": source, "authored": authored]
    let data = try JSONSerialization.data(withJSONObject: request, options: [.sortedKeys])
    let name = "\(Int(now.timeIntervalSince1970 * 1000))-\(UUID().uuidString.prefix(8))\(suffix)"
    let file = directory.appendingPathComponent(name)
    let tmp = directory.appendingPathComponent("." + name + ".tmp")
    try data.write(to: tmp, options: [.atomic])
    try FileManager.default.moveItem(at: tmp, to: file)  // the app never sees half a file
    try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
    return (file, checked.count)
  }

  /// Checks one protocol's answers and writes one request into `directory`.
  @discardableResult
  public static func submitProtocol(_ protocolId: String, _ answers: JSONObject, source: String,
                                    into directory: URL, now: Date = Date()) throws -> (file: URL, answers: Int)
  {
    let checked = try Protocols.validate(protocolId, answers)
    guard checked.count > 0 else { throw HealthGraphError.invalid("no answers to store") }
    let request: JSONObject = ["protocol": protocolId, "answers": answers, "source": source,
                               "authored": ISO8601DateFormatter().string(from: now)]
    return (try write(request, suffix: protocolSuffix, into: directory, now: now), checked.count)
  }

  private static func write(_ request: JSONObject, suffix: String, into directory: URL, now: Date) throws -> URL {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let data = try JSONSerialization.data(withJSONObject: request, options: [.sortedKeys])
    let name = "\(Int(now.timeIntervalSince1970 * 1000))-\(UUID().uuidString.prefix(8))\(suffix)"
    let file = directory.appendingPathComponent(name)
    let tmp = directory.appendingPathComponent("." + name + ".tmp")
    try data.write(to: tmp, options: [.atomic])
    try FileManager.default.moveItem(at: tmp, to: file)  // the app never sees half a file
    try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
    return file
  }

  /// Stores every waiting request in `store`, oldest first. Returns one line per request.
  public static func apply(from directory: URL, to store: HealthStore) -> [String] {
    let fm = FileManager.default
    let files = ((try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? [])
      .filter { $0.lastPathComponent.hasSuffix(suffix) || $0.lastPathComponent.hasSuffix(protocolSuffix) }
      .sorted { $0.lastPathComponent < $1.lastPathComponent }
    var log: [String] = []
    for file in files {
      do {
        let request = try JSON.object(Data(contentsOf: file))
        guard let answers = request["answers"] as? JSONObject else {
          throw HealthGraphError.invalid("a request without answers")
        }
        let source = request["source"] as? String ?? "claude", authored = request["authored"] as? String
        if file.lastPathComponent.hasSuffix(protocolSuffix) {
          guard let id = request["protocol"] as? String else { throw HealthGraphError.invalid("a request without a protocol") }
          let counts = try store.storeProtocol(id, answers, source: source, authored: authored)
          try fm.removeItem(at: file)
          let band = (counts["band"] as? String).map { ", \($0)" } ?? ""
          log.append("\(counts["name"] as? String ?? id): \(counts["answers"] as? Int ?? 0) answers stored\(band)")
          continue
        }
        let counts = try store.storeAnamnesis(answers, source: source, authored: authored)
        try fm.removeItem(at: file)
        log.append("Anamnesis: \(counts["answers"] ?? 0) answers stored")
      } catch {
        let rejected = file.deletingPathExtension().appendingPathExtension("rejected")
        try? fm.removeItem(at: rejected)
        try? fm.moveItem(at: file, to: rejected)
        try? Data("\(error)".utf8).write(to: rejected.appendingPathExtension("reason"))
        log.append("Anamnesis answers refused: \(error)")
      }
    }
    return log
  }
}
