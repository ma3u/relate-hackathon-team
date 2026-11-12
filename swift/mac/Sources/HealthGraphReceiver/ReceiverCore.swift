import Foundation
import HealthGraph

/// What the receiver does with one request, without any networking, so it is
/// easy to test. Port of the Python receiver's handler: same paths, status
/// codes and JSON. All store access runs on one serial queue (one writer).
public final class ReceiverCore: @unchecked Sendable {
  public static let maxBody = 10 * 1024 * 1024

  public struct Request: Sendable {
    public var method: String
    public var path: String
    /// Header names in lower case.
    public var headers: [String: String]
    public var remoteIP: String?
    public var body: Data
    public init(method: String, path: String, headers: [String: String] = [:], remoteIP: String?,
      body: Data = Data())
    {
      self.method = method
      self.path = path
      self.headers = headers
      self.remoteIP = remoteIP
      self.body = body
    }
  }

  public struct Response: Sendable {
    public let status: Int
    public let body: Data
    init(_ status: Int, _ json: [String: Any]) {
      self.status = status
      self.body = (try? JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])) ?? Data("{}".utf8)
    }
  }

  public let store: URL
  let token: String
  let name: String
  let log: @Sendable (String) -> Void
  public let queue = DispatchQueue(label: "health-graph.receiver.store")

  public init(store: URL, token: String, name: String, log: @escaping @Sendable (String) -> Void = { print($0) }) {
    self.store = store
    self.token = token
    self.name = name
    self.log = log
  }

  /// Runs the request on the store queue and calls back with the response.
  public func handle(_ request: Request, completion: @escaping @Sendable (Response) -> Void) {
    queue.async { completion(self.respond(request)) }
  }

  /// Synchronous: call only on `queue` (or in tests with nothing else running).
  public func respond(_ r: Request) -> Response {
    let ip = r.remoteIP ?? "?"
    let response = route(r)
    log("\(ip) \(r.method) \(r.path) \(response.status)")  // never log bodies
    return response
  }

  private func route(_ r: Request) -> Response {
    switch (r.method, r.path) {
    case ("GET", "/v1/status"):
      if let denied = authorize(r) { return denied }
      return status()
    case ("POST", "/v1/record"), ("POST", "/v1/wearables"):
      if let denied = authorize(r) { return denied }
      return post(r)
    default:
      return Response(404, ["error": "not found"])
    }
  }

  private func authorize(_ r: Request) -> Response? {
    guard Network.isPrivate(r.remoteIP) else {
      return Response(403, ["error": "only devices on your own network"])
    }
    guard Network.constantTimeEqual(r.headers["authorization"] ?? "", "Bearer \(token)") else {
      return Response(401, ["error": "scan the QR code again"])
    }
    return nil
  }

  private func status() -> Response {
    var n = 0
    // A read-only open never creates a store.
    if FileManager.default.fileExists(atPath: store.path) {
      do {
        n = try HealthStore(path: store.path, readOnly: true).count("Observation")
      } catch {
        log("status failed: \(error)")
        return Response(503, ["error": "the graph is busy, try again"])
      }
    }
    return Response(200, ["name": name, "store": store.lastPathComponent, "observations": n])
  }

  private func post(_ r: Request) -> Response {
    guard !r.body.isEmpty, r.body.count <= Self.maxBody else {
      return Response(r.body.isEmpty ? 400 : 413, ["error": "a FHIR Bundle up to 10 MB is required"])
    }
    guard let bundle = try? JSON.object(r.body) else { return Response(400, ["error": "not JSON"]) }
    guard bundle["resourceType"] as? String == "Bundle" else {
      return Response(400, ["error": "not a FHIR Bundle"])
    }
    for attempt in 0..<6 {  // another process (a CLI query, MCP) may hold the store
      do {
        return try importBundle(bundle, r)
      } catch let error as HealthGraphError {
        return Response(400, ["error": error.description])
      } catch {
        let locked = ReceiverCore.isBusy(error)
        if locked && attempt < 5 {
          Thread.sleep(forTimeInterval: 0.5 * Double(attempt + 1))
          continue
        }
        log("import failed: \(error)")
        return Response(locked ? 503 : 500, ["error": "the graph could not be written, try again"])
      }
    }
    return Response(503, ["error": "the graph could not be written, try again"])
  }

  /// Another process has the store: "storage locked", or, while a read-only
  /// reader such as `relate serve --mcp` has it open, sometimes a bare
  /// "internal error" (seen Nov 12, 2026). Both pass when retried.
  public static func isBusy(_ error: Error) -> Bool {
    let text = "\(error)".lowercased()
    return text.contains("lock") || text.contains("internal error")
  }

  /// Runs `body`, retrying for a few seconds while another process has the store.
  public static func retrying<T>(_ body: () throws -> T) throws -> T {
    for attempt in 0..<5 {
      do { return try body() } catch where isBusy(error) {
        Thread.sleep(forTimeInterval: 0.5 * Double(attempt + 1))
      }
    }
    return try body()
  }

  private func importBundle(_ bundle: JSONObject, _ r: Request) throws -> Response {
    let graph = try HealthStore(path: store.path)  // closed when this returns
    try graph.initSchema()
    if r.path == "/v1/record" {
      let (stored, parsed) = try graph.receiveReport(bundle, reportId: r.headers["x-klarbefund-report"])
      log("report \(parsed.reportId): \(stored) values")
      return Response(201, [
        "stored": stored, "skipped": parsed.unmapped.map(\.json), "hubReady": parsed.hubReady,
      ])
    }
    let (stored, skipped) = try graph.receiveWearables(bundle)
    log("apple health: \(stored) weekly values")
    return Response(201, ["stored": stored, "skipped": skipped.map(\.json)])
  }
}
