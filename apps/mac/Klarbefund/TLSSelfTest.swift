#if DEBUG
  import CryptoKit
  import Foundation
  import HealthGraphReceiver

  /// Debug only (`--tls-selftest`): the receiver as the iPhone sees it, pinned
  /// certificate and bearer token, on a throwaway identity.
  enum TLSSelfTest {
    static func run() async -> String {
      let dir = FileManager.default.temporaryDirectory.appendingPathComponent("tls-selftest-\(UUID().uuidString)")
      defer { try? FileManager.default.removeItem(at: dir) }
      do {
        // As the iPhone connects: every interface, reached at the LAN address.
        let address = Network.lanAddress()
        let identity = try Identity.ensure(in: dir.appendingPathComponent("pairing"), host: address)
        let core = ReceiverCore(store: dir.appendingPathComponent("health.rl"), token: identity.token, name: "selftest") { _ in }
        let server = try ReceiverServer(core: core, identity: identity)
        defer { server.stop() }
        let port = try server.start(port: 0)
        let pin = Pin(identity.fingerprint)
        let session = URLSession(configuration: .ephemeral, delegate: pin, delegateQueue: nil)
        var r = URLRequest(url: URL(string: "https://\(address):\(port)/v1/status")!)
        r.setValue("Bearer \(identity.token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: r)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let ok = status == 200 && pin.seen == identity.fingerprint
        return "tls-selftest \(ok ? "OK" : "FAILED") via the LAN address: status \(status), pinned \(pin.seen == identity.fingerprint), body \(String(decoding: data, as: UTF8.self))"
      } catch {
        return "tls-selftest FAILED: \(error)"
      }
    }

    final class Pin: NSObject, URLSessionDelegate, @unchecked Sendable {
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
  }
#endif
