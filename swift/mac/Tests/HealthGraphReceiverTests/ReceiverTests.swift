import CoreImage
import CryptoKit
import Foundation
import HealthGraph
import Testing

@testable import HealthGraphReceiver

/// Port of tests/test_receiver.py: HTTPS with a pinned certificate + bearer token.
let repoRoot = URL(fileURLWithPath: #filePath)
  .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
  .deletingLastPathComponent().deletingLastPathComponent()
let golden = repoRoot.appendingPathComponent("fixtures/fhir/2026-09-04-praxis-muster.json")
let wearables = repoRoot.appendingPathComponent("fixtures/apple-health-weekly.json")

func tempDir() throws -> URL {
  let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
  return dir
}

/// Pins the certificate fingerprint, as Klarbefund's PinnedCertificate does.
final class Pinning: NSObject, URLSessionDelegate, @unchecked Sendable {
  let fingerprint: String
  var seen: String?
  init(_ fingerprint: String) { self.fingerprint = fingerprint }
  func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge)
    async -> (URLSession.AuthChallengeDisposition, URLCredential?)
  {
    guard let trust = challenge.protectionSpace.serverTrust,
      let leaf = (SecTrustCopyCertificateChain(trust) as? [SecCertificate])?.first
    else { return (.cancelAuthenticationChallenge, nil) }
    let fp = SHA256.hash(data: SecCertificateCopyData(leaf) as Data).map { String(format: "%02x", $0) }.joined()
    seen = fp
    return fp == fingerprint ? (.useCredential, URLCredential(trust: trust)) : (.cancelAuthenticationChallenge, nil)
  }
}

struct Running {
  let server: ReceiverServer
  let port: Int
  let identity: Identity
  let store: URL
  let session: URLSession

  static func start() throws -> Running {
    let dir = try tempDir()
    let identity = try Identity.ensure(in: dir.appendingPathComponent("config"), host: "127.0.0.1")
    let store = dir.appendingPathComponent("health.rl")
    let core = ReceiverCore(store: store, token: identity.token, name: "test-mac") { _ in }
    let server = try ReceiverServer(core: core, identity: identity)
    let port = try server.start(host: "127.0.0.1", port: 0)
    let session = URLSession(
      configuration: .ephemeral, delegate: Pinning(identity.fingerprint), delegateQueue: nil)
    return Running(server: server, port: port, identity: identity, store: store, session: session)
  }

  func call(_ method: String, _ path: String, body: Data? = nil, token: String? = nil,
    headers: [String: String] = [:]) async throws -> (Int, [String: Any])
  {
    var r = URLRequest(url: URL(string: "https://127.0.0.1:\(port)\(path)")!)
    r.httpMethod = method
    r.httpBody = body
    r.setValue("application/fhir+json", forHTTPHeaderField: "Content-Type")
    if let token { r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
    for (k, v) in headers { r.setValue(v, forHTTPHeaderField: k) }
    let (data, response) = try await session.data(for: r)
    let json = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    return ((response as! HTTPURLResponse).statusCode, json)
  }
}

@Suite("Receiver over HTTPS", .serialized)
struct ReceiverTests {
  @Test func requiresToken() async throws {
    let s = try Running.start()
    defer { s.server.stop() }
    #expect(try await s.call("GET", "/v1/status").0 == 401)
    #expect(try await s.call("GET", "/v1/status", token: "wrong").0 == 401)
    let (status, body) = try await s.call("GET", "/v1/status", token: s.identity.token)
    #expect(status == 200 && body["name"] as? String == "test-mac")
    #expect(body["observations"] as? Int == 0)
    #expect(!FileManager.default.fileExists(atPath: s.store.path))  // status never creates a store
  }

  @Test func recordThenWearables() async throws {
    let s = try Running.start()
    defer { s.server.stop() }
    let bundle = try Data(contentsOf: golden)
    let header = ["X-Klarbefund-Report": "3f2a-report-uuid"]
    var (status, body) = try await s.call("POST", "/v1/record", body: bundle, token: s.identity.token, headers: header)
    #expect(status == 201 && body["stored"] as? Int == 7 && body["hubReady"] as? Int == 6)
    #expect((body["skipped"] as? [Any])?.count == 1)  // the microbiome value without LOINC

    // sending the same report again replaces it
    (status, body) = try await s.call("POST", "/v1/record", body: bundle, token: s.identity.token, headers: header)
    #expect(body["stored"] as? Int == 7)

    (status, body) = try await s.call("POST", "/v1/wearables", body: Data(contentsOf: wearables), token: s.identity.token)
    #expect(status == 201 && body["stored"] as? Int == 16 && (body["skipped"] as? [Any])?.isEmpty == true)

    (status, body) = try await s.call("GET", "/v1/status", token: s.identity.token)
    #expect(body["observations"] as? Int == 7 + 16)

    let graph = try await s.server.core.queue.sync { try HealthStore(path: s.store.path, readOnly: true) }
    let weight = try graph.connection.query(
      """
      MATCH (o:Observation)-[:CODED_BY]->(:LoincCode {code: '29463-7'})
      RETURN o.sourceKind AS kind, count(*) AS n ORDER BY kind
      """
    ).records
    // weight from the lab sheet and from Apple Health meet on one LoincCode
    #expect(weight.map { $0["kind"]?.plain ?? "" } == ["device-weekly-mean", "ocr-transcribed"])
    #expect(weight.map { $0["n"]?.intValue ?? 0 } == [4, 1])
  }

  @Test func aStalledClientDoesNotBlockOthers() async throws {
    let s = try Running.start()
    defer { s.server.stop() }
    // A TCP connection that never sends a TLS hello.
    let idle = socket(AF_INET, SOCK_STREAM, 0)
    defer { close(idle) }
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = in_port_t(s.port).bigEndian
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr)
    _ = withUnsafePointer(to: &addr) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        connect(idle, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
      }
    }
    #expect(try await s.call("GET", "/v1/status", token: s.identity.token).0 == 200)
  }

  @Test func concurrentSendsAndStatus() async throws {
    let s = try Running.start()
    defer { s.server.stop() }
    let bundle = try Data(contentsOf: golden)
    let wear = try Data(contentsOf: wearables)
    let token = s.identity.token
    let statuses = try await withThrowingTaskGroup(of: Int.self) { group in
      for i in 0..<3 {
        group.addTask { try await s.call("POST", "/v1/record", body: bundle, token: token, headers: ["X-Klarbefund-Report": "r\(i)"]).0 }
      }
      for _ in 0..<2 {
        group.addTask { try await s.call("POST", "/v1/wearables", body: wear, token: token).0 }
        group.addTask { try await s.call("GET", "/v1/status", token: token).0 }
      }
      return try await group.reduce(into: [Int]()) { $0.append($1) }
    }
    #expect(statuses.allSatisfy { $0 == 200 || $0 == 201 }, "\(statuses)")
    let (_, body) = try await s.call("GET", "/v1/status", token: token)
    #expect(body["observations"] as? Int == 3 * 7 + 16)
  }

  @Test func rejectsNonBundleAndNonJSON() async throws {
    let s = try Running.start()
    defer { s.server.stop() }
    let patient = Data(#"{"resourceType": "Patient"}"#.utf8)
    #expect(try await s.call("POST", "/v1/record", body: patient, token: s.identity.token).0 == 400)
    #expect(try await s.call("POST", "/v1/record", body: Data("nope".utf8), token: s.identity.token).0 == 400)
    #expect(try await s.call("POST", "/v1/record", token: s.identity.token).0 == 400)
    #expect(try await s.call("GET", "/v2/anything", token: s.identity.token).0 == 404)
  }
}

@Suite("Identity, pairing, network rules")
struct PairingTests {
  @Test func pairingLinkRoundTrip() throws {
    let dir = try tempDir()
    let id = try Identity.ensure(in: dir, host: "192.168.1.20")
    let link = Pairing.link(
      url: "https://192.168.1.20:8787", token: id.token, fingerprint: id.fingerprint, name: "my mac",
      store: "health.rl")
    let u = try #require(URLComponents(string: link))
    #expect(u.scheme == "klarbefund" && u.host == "relate")
    let q = Dictionary(uniqueKeysWithValues: (u.queryItems ?? []).map { ($0.name, $0.value ?? "") })
    #expect(
      q == [
        "url": "https://192.168.1.20:8787", "token": id.token, "fp": id.fingerprint, "name": "my mac",
        "store": "health.rl",
      ])
    #expect(id.fingerprint.count == 64 && id.token.count >= 43)
    let mode = try FileManager.default.attributesOfItem(atPath: id.key.path)[.posixPermissions] as! Int
    #expect(mode & 0o077 == 0)
    // a second start keeps the same identity (the paired phone keeps working)
    let again = try Identity.ensure(in: dir, host: "192.168.1.20")
    #expect(again.fingerprint == id.fingerprint && again.token == id.token)
    #expect(try Identity.ensure(in: dir, rotate: true, host: "192.168.1.20").token != id.token)
  }

  /// Apple's TLS refuses a v1 certificate and explicit curve parameters.
  @Test func certificateIsX509v3NamedCurveForServerAuth() throws {
    let id = try Identity.ensure(in: try tempDir(), host: "192.168.1.20")
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/openssl")
    p.arguments = ["x509", "-in", id.certificate.path, "-noout", "-text"]
    let pipe = Pipe()
    p.standardOutput = pipe
    try p.run()
    p.waitUntilExit()
    let text = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
    #expect(text.contains("Version: 3"))
    #expect(text.contains("IP Address:127.0.0.1") && text.contains("IP Address:192.168.1.20"))
    #expect(text.contains("TLS Web Server Authentication"))
    #expect(text.contains("prime256v1") && !text.contains("Field Type: prime-field"))
  }

  @Test func replacesAnUnusableCertificate() throws {
    let dir = try tempDir()
    let id = try Identity.ensure(in: dir, host: "127.0.0.1")
    try "not a certificate".write(to: id.certificate, atomically: true, encoding: .utf8)
    let fresh = try Identity.ensure(in: dir, host: "127.0.0.1")
    #expect(fresh.fingerprint != id.fingerprint && fresh.token == id.token)
  }

  @Test func privateNetworkRule() {
    for ip in ["127.0.0.1", "10.1.2.3", "172.16.0.1", "172.31.255.1", "192.168.1.20", "169.254.1.1",
      "::1", "fe80::1", "fd00::1", "::ffff:192.168.1.5"]
    {
      #expect(Network.isPrivate(ip), "\(ip)")
    }
    for ip in ["8.8.8.8", "172.32.0.1", "100.64.0.1", "2001:db8::1", "::ffff:8.8.8.8", "nonsense", ""] {
      #expect(!Network.isPrivate(ip), "\(ip)")
    }
    #expect(!Network.isPrivate(nil))
  }

  @Test func constantTimeEqual() {
    #expect(Network.constantTimeEqual("Bearer abc", "Bearer abc"))
    #expect(!Network.constantTimeEqual("Bearer abc", "Bearer abd"))
    #expect(!Network.constantTimeEqual("Bearer ab", "Bearer abc"))
  }

  @Test func requireMountRefusesAPlainFolder() throws {
    #expect(!Network.isMountPoint(try tempDir()))
    #expect(Network.isMountPoint(URL(fileURLWithPath: "/")))
  }

  @Test func qrCodeDecodesToTheLink() throws {
    let link = Pairing.link(
      url: "https://192.168.1.20:8787", token: Identity.newToken(), fingerprint: String(repeating: "ab", count: 32),
      name: "my-mac", store: "health.rl")
    let qr = try #require(QRCode(link))
    let png = try #require(qr.png())
    let image = try #require(CIImage(data: png))
    let detector = try #require(
      CIDetector(ofType: CIDetectorTypeQRCode, context: nil, options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]))
    let found = detector.features(in: image).compactMap { ($0 as? CIQRCodeFeature)?.messageString }
    #expect(found == [link])
    #expect(qr.terminal().contains("\u{2580}"))
  }
}
