import CryptoKit
import Foundation
import Security
import SwiftASN1

/// The receiver's TLS certificate, key and pairing token.
///
/// Same files and format as the Python receiver (`~/.config/relate-health-graph`:
/// cert.pem, key.pem, token), so a phone paired with either keeps working.
public struct Identity: Sendable {
  public let certificate: URL
  public let key: URL
  public let token: String
  /// SHA-256 of the certificate (DER), hex. The QR code carries it; the app pins it.
  public let fingerprint: String

  public static var defaultDirectory: URL {
    if let home = ProcessInfo.processInfo.environment["RELATE_HEALTH_HOME"] {
      return URL(fileURLWithPath: home)
    }
    return FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".config/relate-health-graph")
  }

  /// Loads the identity, making what is missing. A certificate Apple's TLS would
  /// refuse (not X.509 v3, not a named P-256 key) is replaced. `rotate` makes a
  /// new token, so phones paired before must scan again.
  public static func ensure(in dir: URL = defaultDirectory, rotate: Bool = false, host: String)
    throws -> Identity
  {
    let fm = FileManager.default
    try fm.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    let cert = dir.appendingPathComponent("cert.pem")
    let key = dir.appendingPathComponent("key.pem")
    let tokenFile = dir.appendingPathComponent("token")

    if !fm.fileExists(atPath: key.path) || !certificateIsUsable(cert) {
      try makeCertificate(cert: cert, key: key, lanAddress: host)
    }
    if rotate || !fm.fileExists(atPath: tokenFile.path) {
      try writePrivate(newToken(), to: tokenFile)
    }
    let token = try String(contentsOf: tokenFile, encoding: .utf8)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let der = try PEMDocument(pemString: String(contentsOf: cert, encoding: .utf8)).derBytes
    let fingerprint = SHA256.hash(data: der).map { String(format: "%02x", $0) }.joined()
    return Identity(certificate: cert, key: key, token: token, fingerprint: fingerprint)
  }

  /// X.509 v3 with a named-curve P-256 key: what Apple's TLS stack accepts.
  static func certificateIsUsable(_ url: URL) -> Bool {
    guard let pem = try? String(contentsOf: url, encoding: .utf8),
      let der = try? PEMDocument(pemString: pem).derBytes,
      let cert = SecCertificateCreateWithData(nil, Data(der) as CFData),
      let key = SecCertificateCopyKey(cert),
      let attributes = SecKeyCopyAttributes(key) as? [CFString: Any]
    else { return false }
    let p256 = (attributes[kSecAttrKeyType] as? String) == (kSecAttrKeyTypeECSECPrimeRandom as String)
      && (attributes[kSecAttrKeySizeInBits] as? Int) == 256
    return p256 && DER.isVersion3(der)
  }

  /// A self-signed P-256 certificate for TLS server authentication, written as
  /// DER by hand and signed with CryptoKit: no crypto library is bundled.
  static func makeCertificate(cert: URL, key: URL, lanAddress: String) throws {
    let privateKey = P256.Signing.PrivateKey()
    let host = ProcessInfo.processInfo.hostName.split(separator: ".").first.map(String.init) ?? "mac"
    var sans = [DER.context(2, Array("localhost".utf8)), DER.context(2, Array("\(host).local".utf8))]
    for ip in Set(["127.0.0.1", lanAddress]).sorted() {
      if let bytes = ipv4Bytes(ip) { sans.append(DER.context(7, bytes)) }
    }
    let now = Date()
    let der = try DER.selfSignedCertificate(
      key: privateKey, commonName: "Relate Health Graph (local)",
      notBefore: now.addingTimeInterval(-3600), notAfter: now.addingTimeInterval(825 * 86400),
      subjectAltNames: sans)
    let pem = PEMDocument(type: "CERTIFICATE", derBytes: der).pemString
    try writePrivate(privateKey.pemRepresentation + "\n", to: key)
    try (pem + "\n").write(to: cert, atomically: true, encoding: .utf8)
  }

  /// 256 random bits, base64url without padding (Python's `secrets.token_urlsafe(32)`).
  static func newToken() -> String {
    var bytes = [UInt8](repeating: 0, count: 32)
    precondition(SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess)
    return Data(bytes).base64EncodedString()
      .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }

  static func writePrivate(_ text: String, to url: URL) throws {
    try? FileManager.default.removeItem(at: url)
    guard FileManager.default.createFile(atPath: url.path, contents: Data(text.utf8),
      attributes: [.posixPermissions: 0o600])
    else { throw CocoaError(.fileWriteUnknown, userInfo: [NSFilePathErrorKey: url.path]) }
  }

  static func ipv4Bytes(_ ip: String) -> [UInt8]? {
    let parts = ip.split(separator: ".").compactMap { UInt8($0) }
    return parts.count == 4 ? parts : nil
  }
}
