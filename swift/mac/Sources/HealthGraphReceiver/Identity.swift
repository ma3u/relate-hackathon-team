import Crypto
import Foundation
import SwiftASN1
import X509

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
      let cert = try? Certificate(pemEncoded: pem)
    else { return false }
    return cert.version == .v3 && P256.Signing.PublicKey(cert.publicKey) != nil
  }

  static func makeCertificate(cert: URL, key: URL, lanAddress: String) throws {
    let privateKey = P256.Signing.PrivateKey()
    let name = try DistinguishedName { CommonName("Relate Health Graph (local)") }
    let host = ProcessInfo.processInfo.hostName.split(separator: ".").first.map(String.init) ?? "mac"
    var sans: [GeneralName] = [.dnsName("localhost"), .dnsName("\(host).local")]
    for ip in Set(["127.0.0.1", lanAddress]) {
      if let bytes = ipv4Bytes(ip) { sans.append(.ipAddress(ASN1OctetString(contentBytes: bytes[...]))) }
    }
    let now = Date()
    let certificate = try Certificate(
      version: .v3,
      serialNumber: Certificate.SerialNumber(),
      publicKey: .init(privateKey.publicKey),
      notValidBefore: now.addingTimeInterval(-3600),
      notValidAfter: now.addingTimeInterval(825 * 86400),
      issuer: name,
      subject: name,
      signatureAlgorithm: .ecdsaWithSHA256,
      extensions: try Certificate.Extensions {
        Critical(BasicConstraints.notCertificateAuthority)
        Critical(KeyUsage(digitalSignature: true))
        try ExtendedKeyUsage([.serverAuth])
        SubjectAlternativeNames(sans)
      },
      issuerPrivateKey: .init(privateKey))
    try writePrivate(privateKey.pemRepresentation + "\n", to: key)
    try (try certificate.serializeAsPEM().pemString + "\n").write(to: cert, atomically: true, encoding: .utf8)
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
