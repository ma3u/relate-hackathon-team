import CryptoKit
import Foundation
import Network
import Security
import SwiftASN1

/// The receiver's certificate and key as a keychain identity, which is what the
/// Network framework's TLS takes. The PEM files stay the source of truth (the
/// pinned fingerprint is theirs); the keychain holds a copy while the server
/// runs. Signed apps use the data-protection keychain (this app only); other
/// processes, like the tests, fall back to the login keychain.
final class TLSIdentity {
  let secIdentity: sec_identity_t
  private let label: String
  private let dataProtection: Bool

  enum Failure: Error, CustomStringConvertible {
    case key, certificate, keychain(OSStatus), noIdentity
    var description: String {
      switch self {
      case .key: return "the receiver key is not a P-256 private key"
      case .certificate: return "the receiver certificate could not be read"
      case .keychain(let status): return "the keychain refused the receiver identity (\(status))"
      case .noIdentity: return "the keychain holds no identity for the receiver certificate"
      }
    }
  }

  /// Refs of what went into the login keychain (fallback), to remove them again.
  private var added: [(CFString, CFTypeRef)] = []

  init(_ identity: Identity) throws {
    let pemKey = try String(contentsOf: identity.key, encoding: .utf8)
    guard let p256 = try? P256.Signing.PrivateKey(pemRepresentation: pemKey) else { throw Failure.key }
    let der = Data(try PEMDocument(pemString: String(contentsOf: identity.certificate, encoding: .utf8)).derBytes)
    guard let cert = SecCertificateCreateWithData(nil, der as CFData) else { throw Failure.certificate }
    label = "Relate Health Graph receiver " + identity.fingerprint.prefix(16)

    // The data-protection keychain first; any failure there (no application
    // identifier, as in `swift test` and local builds, or anything else) falls
    // back to the login keychain, which works sandboxed or not.
    if Self.addDataProtection(p256, cert: cert, label: label) == errSecSuccess,
      let found = Self.identity(for: der, dataProtection: true), let sec = sec_identity_create(found)
    {
      dataProtection = true
      secIdentity = sec
      return
    }
    Self.delete(label: label)
    dataProtection = false
    added = try Self.addLoginKeychain(p256, cert: cert, der: der)
    guard let found = Self.identity(for: der, dataProtection: false), let sec = sec_identity_create(found) else {
      for (cls, ref) in added { SecItemDelete([kSecClass: cls, kSecValueRef: ref] as CFDictionary) }
      throw Failure.noIdentity
    }
    secIdentity = sec
  }

  /// Removes this identity's keychain copy (the PEM files stay).
  func remove() {
    if dataProtection {
      Self.delete(label: label)
    } else {
      for (cls, ref) in added { SecItemDelete([kSecClass: cls, kSecValueRef: ref] as CFDictionary) }
      added = []
    }
  }

  /// The data-protection keychain, for apps signed with an application identifier.
  private static func addDataProtection(_ p256: P256.Signing.PrivateKey, cert: SecCertificate, label: String)
    -> OSStatus
  {
    var error: Unmanaged<CFError>?
    guard
      let key = SecKeyCreateWithData(
        p256.x963Representation as CFData,
        [kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom, kSecAttrKeyClass: kSecAttrKeyClassPrivate,
         kSecAttrKeySizeInBits: 256] as CFDictionary, &error)
    else { return errSecParam }
    delete(label: label)
    let common: [CFString: Any] = [
      kSecAttrLabel: label, kSecUseDataProtectionKeychain: true,
      kSecAttrAccessible: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
    ]
    var status = SecItemAdd(
      common.merging([kSecClass: kSecClassKey, kSecValueRef: key]) { $1 } as CFDictionary, nil)
    guard status == errSecSuccess || status == errSecDuplicateItem else { return status }
    status = SecItemAdd(common.merging([kSecClass: kSecClassCertificate, kSecValueRef: cert]) { $1 } as CFDictionary, nil)
    return status == errSecDuplicateItem ? errSecSuccess : status
  }

  private static func delete(label: String) {
    for cls in [kSecClassKey, kSecClassCertificate] {
      SecItemDelete([kSecClass: cls, kSecAttrLabel: label, kSecUseDataProtectionKeychain: true] as CFDictionary)
    }
  }

  /// The login keychain, for unsigned processes. It takes an EC key only as an
  /// imported SEC1 ("EC PRIVATE KEY") document.
  private static func addLoginKeychain(_ p256: P256.Signing.PrivateKey, cert: SecCertificate, der: Data) throws
    -> [(CFString, CFTypeRef)]
  {
    if let old = identity(for: der, dataProtection: false) {  // left over from a run that crashed
      var key: SecKey?
      if SecIdentityCopyPrivateKey(old, &key) == errSecSuccess, let key {
        SecItemDelete([kSecClass: kSecClassKey, kSecValueRef: key] as CFDictionary)
      }
      var oldCert: SecCertificate?
      if SecIdentityCopyCertificate(old, &oldCert) == errSecSuccess, let oldCert {
        SecItemDelete([kSecClass: kSecClassCertificate, kSecValueRef: oldCert] as CFDictionary)
      }
    }
    var format = SecExternalFormat.formatOpenSSL
    var type = SecExternalItemType.itemTypePrivateKey
    var items: CFArray?
    var keychain: SecKeychain?
    SecKeychainCopyDefault(&keychain)
    let status = SecItemImport(sec1(p256) as CFData, "der" as CFString, &format, &type, [], nil, keychain, &items)
    guard status == errSecSuccess, let key = (items as? [SecKey])?.first else { throw Failure.keychain(status) }
    var added: [(CFString, CFTypeRef)] = [(kSecClassKey, key)]
    let certStatus = SecItemAdd([kSecClass: kSecClassCertificate, kSecValueRef: cert] as CFDictionary, nil)
    if certStatus == errSecSuccess { added.append((kSecClassCertificate, cert)) }
    else if certStatus != errSecDuplicateItem { throw Failure.keychain(certStatus) }
    return added
  }

  /// RFC 5915 ECPrivateKey for P-256: version, d, the curve, the public point.
  static func sec1(_ key: P256.Signing.PrivateKey) -> Data {
    func tlv(_ tag: UInt8, _ body: [UInt8]) -> [UInt8] {
      [tag] + (body.count < 128 ? [UInt8(body.count)] : [0x81, UInt8(body.count)]) + body
    }
    let prime256v1: [UInt8] = [0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07]
    let body = [0x02, 0x01, 0x01] + tlv(0x04, Array(key.rawRepresentation)) + tlv(0xa0, prime256v1)
      + tlv(0xa1, tlv(0x03, [0x00] + Array(key.publicKey.x963Representation)))
    return Data(tlv(0x30, body))
  }

  /// The keychain identity whose certificate is exactly ours.
  private static func identity(for der: Data, dataProtection: Bool) -> SecIdentity? {
    var result: CFTypeRef?
    let query: [CFString: Any] = [
      kSecClass: kSecClassIdentity, kSecReturnRef: true, kSecMatchLimit: kSecMatchLimitAll,
      kSecUseDataProtectionKeychain: dataProtection,
    ]
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
      let all = result as? [SecIdentity]
    else { return nil }
    return all.first { id in
      var cert: SecCertificate?
      return SecIdentityCopyCertificate(id, &cert) == errSecSuccess
        && cert.map { SecCertificateCopyData($0) as Data } == der
    }
  }
}
