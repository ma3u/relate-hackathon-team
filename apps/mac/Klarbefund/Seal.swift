import CryptoKit
import Foundation
import Security

/// The graph at rest: while Klarbefund for Mac is closed, `health.rl` exists only
/// as `health.rl.sealed`, AES-256-GCM with a key that never leaves this Mac's
/// keychain. Opening the app unseals it; quitting seals it again.
enum Seal {
  private static let service = "red.mabu.meinbefund.graph-key"
  private static let account = "health.rl"

  static func open(sealed: URL, into store: URL) throws {
    let fm = FileManager.default
    guard fm.fileExists(atPath: sealed.path) else { return }
    // A store newer than the seal means the app stopped without sealing: keep it.
    if fm.fileExists(atPath: store.path), modified(store) >= modified(sealed) {
      try fm.removeItem(at: sealed)
      return
    }
    let box = try AES.GCM.SealedBox(combined: Data(contentsOf: sealed))
    let plain = try AES.GCM.open(box, using: key())
    try write(plain, to: store)
    try fm.removeItem(at: sealed)
  }

  static func close(_ store: URL, into sealed: URL) throws {
    let fm = FileManager.default
    guard fm.fileExists(atPath: store.path) else { return }
    let box = try AES.GCM.seal(Data(contentsOf: store), using: key())
    guard let combined = box.combined else { throw CocoaError(.fileWriteUnknown) }
    try write(combined, to: sealed)
    try fm.removeItem(at: store)
  }

  private static func write(_ data: Data, to url: URL) throws {
    try data.write(to: url, options: [.atomic])
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
  }

  private static func modified(_ url: URL) -> Date {
    (try? FileManager.default.attributesOfItem(atPath: url.path)[.modificationDate] as? Date) ?? .distantPast
  }

  /// The 256-bit key, made once and kept in the keychain (this device only).
  private static func key() throws -> SymmetricKey {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
      kSecAttrAccount as String: account, kSecReturnData as String: true,
    ]
    var item: CFTypeRef?
    if SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data {
      return SymmetricKey(data: data)
    }
    let key = SymmetricKey(size: .bits256)
    let data = key.withUnsafeBytes { Data($0) }
    let add: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
      kSecAttrAccount as String: account, kSecValueData as String: data,
      kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
      kSecAttrLabel as String: "Klarbefund health graph key",
    ]
    let status = SecItemAdd(add as CFDictionary, nil)
    guard status == errSecSuccess else {
      throw NSError(domain: NSOSStatusErrorDomain, code: Int(status),
                    userInfo: [NSLocalizedDescriptionKey: "The keychain refused the graph key (\(status))."])
    }
    return key
  }
}
