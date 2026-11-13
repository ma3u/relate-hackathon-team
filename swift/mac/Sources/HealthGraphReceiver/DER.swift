import CryptoKit
import Foundation
import Security

/// Just enough DER (X.690) for the receiver's self-signed certificate.
enum DER {
  static func tlv(_ tag: UInt8, _ body: [UInt8]) -> [UInt8] {
    let n = body.count
    let length: [UInt8] =
      n < 0x80 ? [UInt8(n)] : n <= 0xFF ? [0x81, UInt8(n)] : [0x82, UInt8(n >> 8), UInt8(n & 0xFF)]
    return [tag] + length + body
  }
  static func sequence(_ parts: [UInt8]...) -> [UInt8] { tlv(0x30, parts.flatMap { $0 }) }
  static func set(_ parts: [UInt8]...) -> [UInt8] { tlv(0x31, parts.flatMap { $0 }) }
  static func oid(_ bytes: [UInt8]) -> [UInt8] { tlv(0x06, bytes) }
  static func octets(_ body: [UInt8]) -> [UInt8] { tlv(0x04, body) }
  static func bits(_ body: [UInt8]) -> [UInt8] { tlv(0x03, [0x00] + body) }
  static let `true`: [UInt8] = [0x01, 0x01, 0xFF]
  /// Implicitly tagged primitive, e.g. GeneralName dNSName [2] / iPAddress [7].
  static func context(_ n: UInt8, _ body: [UInt8]) -> [UInt8] { tlv(0x80 | n, body) }
  /// Explicitly tagged constructed, e.g. TBSCertificate version [0] / extensions [3].
  static func explicit(_ n: UInt8, _ body: [UInt8]) -> [UInt8] { tlv(0xA0 | n, body) }

  static func integer(_ magnitude: [UInt8]) -> [UInt8] {
    var b = Array(magnitude.drop { $0 == 0 })
    if b.isEmpty { b = [0] }
    if b[0] & 0x80 != 0 { b.insert(0, at: 0) }
    return tlv(0x02, b)
  }

  static func utcTime(_ date: Date) -> [UInt8] {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = TimeZone(identifier: "UTC")
    f.dateFormat = "yyMMddHHmmss'Z'"
    return tlv(0x17, Array(f.string(from: date).utf8))
  }

  static let ecdsaWithSHA256 = sequence(oid([0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x04, 0x03, 0x02]))

  static func extensionField(_ id: [UInt8], critical: Bool, _ value: [UInt8]) -> [UInt8] {
    sequence(oid(id), critical ? `true` : [], octets(value))
  }

  /// X.509 v3, self-signed, ECDSA P-256 with SHA-256, for TLS server authentication.
  static func selfSignedCertificate(
    key: P256.Signing.PrivateKey, commonName: String, notBefore: Date, notAfter: Date,
    subjectAltNames: [[UInt8]]
  ) throws -> [UInt8] {
    var serial = [UInt8](repeating: 0, count: 16)
    guard SecRandomCopyBytes(kSecRandomDefault, serial.count, &serial) == errSecSuccess else {
      throw CocoaError(.featureUnsupported)
    }
    serial[0] &= 0x7F
    let name = sequence(set(sequence(oid([0x55, 0x04, 0x03]), tlv(0x0C, Array(commonName.utf8)))))
    let extensions = sequence(
      extensionField([0x55, 0x1D, 0x13], critical: true, sequence()),  // basicConstraints: not a CA
      extensionField([0x55, 0x1D, 0x0F], critical: true, tlv(0x03, [0x07, 0x80])),  // keyUsage: digitalSignature
      extensionField([0x55, 0x1D, 0x25], critical: false,  // extKeyUsage: serverAuth
        sequence(oid([0x2B, 0x06, 0x01, 0x05, 0x05, 0x07, 0x03, 0x01]))),
      extensionField([0x55, 0x1D, 0x11], critical: false, tlv(0x30, subjectAltNames.flatMap { $0 })))
    let tbs = sequence(
      explicit(0, integer([2])),  // v3
      integer(serial),
      ecdsaWithSHA256,
      name,
      sequence(utcTime(notBefore), utcTime(notAfter)),
      name,
      Array(key.publicKey.derRepresentation),  // SubjectPublicKeyInfo, named curve
      explicit(3, extensions))
    let signature = try key.signature(for: Data(tbs)).derRepresentation
    return sequence(tbs, ecdsaWithSHA256, bits(Array(signature)))
  }

  /// Certificate → TBSCertificate → version [0] INTEGER 2.
  static func isVersion3(_ der: [UInt8]) -> Bool {
    func header(_ at: Int) -> Int? {  // offset of the content after a tag and length
      guard at + 1 < der.count else { return nil }
      let first = der[at + 1]
      return first < 0x80 ? at + 2 : at + 2 + Int(first & 0x7F)
    }
    guard der.first == 0x30, let tbs = header(0), tbs < der.count, der[tbs] == 0x30,
      let v = header(tbs), v + 5 <= der.count
    else { return false }
    return Array(der[v..<v + 5]) == [0xA0, 0x03, 0x02, 0x01, 0x02]
  }
}
