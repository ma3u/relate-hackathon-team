import Darwin
import Foundation

/// Small network helpers shared by the receiver and the CLI.
public enum Network {
  /// The address other devices on the Wi-Fi reach this Mac at.
  public static func lanAddress() -> String {
    let fd = socket(AF_INET, SOCK_DGRAM, 0)
    guard fd >= 0 else { return "127.0.0.1" }
    defer { close(fd) }
    var target = sockaddr_in()
    target.sin_family = sa_family_t(AF_INET)
    target.sin_port = in_port_t(9).bigEndian
    inet_pton(AF_INET, "192.0.2.1", &target.sin_addr)  // TEST-NET: nothing is sent
    let connected = withUnsafePointer(to: &target) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
      }
    }
    guard connected == 0 else { return "127.0.0.1" }
    var local = sockaddr_in()
    var length = socklen_t(MemoryLayout<sockaddr_in>.size)
    let named = withUnsafeMutablePointer(to: &local) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) }
    }
    guard named == 0 else { return "127.0.0.1" }
    var buffer = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
    inet_ntop(AF_INET, &local.sin_addr, &buffer, socklen_t(buffer.count))
    return String(cString: buffer)
  }

  /// A TCP connection to 127.0.0.1:`port`, or nil when nothing listens there.
  public static func connectLoopback(port: UInt16) -> Int32? {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else { return nil }
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = port.bigEndian
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr)
    let ok = withUnsafePointer(to: &addr) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
      }
    }
    if ok != 0 {
      close(fd)
      return nil
    }
    return fd
  }

  /// This Mac's short name, as the app shows it.
  public static var hostName: String {
    ProcessInfo.processInfo.hostName.split(separator: ".").first.map(String.init) ?? "Mac"
  }

  /// Private, loopback or link-local (the Python receiver's `ipaddress` rule).
  public static func isPrivate(_ host: String?) -> Bool {
    guard var host else { return false }
    if host.lowercased().hasPrefix("::ffff:"), host.contains(".") { host = String(host.dropFirst(7)) }
    var v4 = in_addr()
    if inet_pton(AF_INET, host, &v4) == 1 {
      let b = withUnsafeBytes(of: v4.s_addr) { Array($0) }  // network byte order
      return b[0] == 10 || b[0] == 127 || (b[0] == 172 && (16...31).contains(b[1]))
        || (b[0] == 192 && b[1] == 168) || (b[0] == 169 && b[1] == 254)
    }
    var v6 = in6_addr()
    if inet_pton(AF_INET6, host, &v6) == 1 {
      let b = withUnsafeBytes(of: v6) { Array($0) }
      let loopback = b.dropLast().allSatisfy { $0 == 0 } && b[15] == 1
      return loopback || (b[0] & 0xFE) == 0xFC || (b[0] == 0xFE && (b[1] & 0xC0) == 0x80)
    }
    return false
  }

  /// Compares secrets without leaking where they differ.
  public static func constantTimeEqual(_ a: String, _ b: String) -> Bool {
    let x = Array(a.utf8)
    let y = Array(b.utf8)
    var diff = UInt8(x.count == y.count ? 0 : 1)
    for i in 0..<max(x.count, y.count) {
      diff |= (i < x.count ? x[i] : 0) ^ (i < y.count ? y[i] : 0)
    }
    return diff == 0
  }

  /// True when `folder` is the root of a mounted volume (the encrypted vault),
  /// not an empty mount-point folder on the system disk.
  public static func isMountPoint(_ folder: URL) -> Bool {
    var own = stat()
    var parent = stat()
    guard stat(folder.path, &own) == 0,
      stat(folder.deletingLastPathComponent().path, &parent) == 0
    else { return false }
    return own.st_dev != parent.st_dev || own.st_ino == parent.st_ino
  }
}

/// The `klarbefund://relate?...` link the QR code carries.
public enum Pairing {
  public static func link(url: String, token: String, fingerprint: String, name: String, store: String)
    -> String
  {
    "klarbefund://relate?url=\(q(url))&token=\(q(token))&fp=\(fingerprint)&name=\(q(name))&store=\(q(store))"
  }

  /// Python's `quote(s, safe="")`: everything but unreserved ASCII is escaped.
  static func q(_ s: String) -> String {
    let unreserved = CharacterSet(
      charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    return s.addingPercentEncoding(withAllowedCharacters: unreserved) ?? s
  }
}
