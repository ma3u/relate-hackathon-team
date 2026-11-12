import Darwin
import Foundation
import HealthGraph

/// Klarbefund -> Mac over the USB cable, without Wi-Fi.
///
/// macOS's usbmuxd (the service Finder, Xcode and Music use for a connected
/// iPhone) opens a TCP connection to a port on the phone's loopback. While
/// "Send over USB cable" is open, Klarbefund listens there. The Mac proves it
/// is the paired one with the pairing token; only then does the phone send
/// its report bundles and Apple Health weekly means, which go into the graph
/// through the same code as the Wi-Fi receiver.
///
/// Frames both ways: a 4-byte big-endian length, then JSON.
///   Mac   -> phone  {"token": "..."}
///   phone -> Mac    {"type": "record", "report": "<id>", "bundle": {...}} ...
///                   {"type": "wearables", "bundle": {...}}
///                   {"type": "end"}            or {"type": "error", "error": "..."}
///   Mac   -> phone  {"stored": n, "reports": n, "weekly": n, "skipped": n}
public enum USB {
  /// The port Klarbefund listens on (phone loopback only).
  public static let port: UInt16 = 8788
  static let maxFrame = 10 * 1024 * 1024

  public struct Summary: Equatable, Sendable {
    public var reports = 0
    public var stored = 0
    public var weekly = 0
    public var skipped = 0
    public var json: [String: Any] {
      ["reports": reports, "stored": stored, "weekly": weekly, "skipped": skipped]
    }
  }

  public enum Failure: Error, CustomStringConvertible {
    case usbmuxd(String)
    case refused
    case phone(String)
    case protocolError(String)
    public var description: String {
      switch self {
      case .usbmuxd(let m): "usbmuxd: \(m)"
      case .refused: "the phone is not listening (open Klarbefund: Export to my Mac -> Send over USB cable)"
      case .phone(let m): "the phone said: \(m)"
      case .protocolError(let m): "unexpected data from the phone: \(m)"
      }
    }
  }

  /// Sends the token, imports every frame the phone sends, answers with the summary.
  public static func pull(_ stream: FrameStream, token: String, store: URL, log: (String) -> Void)
    throws -> Summary
  {
    try stream.write(["token": token])
    var summary = Summary()
    let graph = try ReceiverCore.retrying { try HealthStore(path: store.path) }  // closed when this returns
    try ReceiverCore.retrying { try graph.initSchema() }
    while true {
      let frame = try stream.read()
      switch frame["type"] as? String {
      case "record":
        guard let bundle = frame["bundle"] as? JSONObject else {
          throw Failure.protocolError("a record without a bundle")
        }
        let report = frame["report"] as? String
        let (stored, parsed) = try ReceiverCore.retrying { try graph.receiveReport(bundle, reportId: report) }
        summary.reports += 1
        summary.stored += stored
        summary.skipped += parsed.unmapped.count
        log("report \(parsed.reportId): \(stored) values")
      case "wearables":
        guard let bundle = frame["bundle"] as? JSONObject else {
          throw Failure.protocolError("wearables without a bundle")
        }
        let (stored, skipped) = try ReceiverCore.retrying { try graph.receiveWearables(bundle) }
        summary.weekly += stored
        summary.skipped += skipped.count
        log("apple health: \(stored) weekly values")
      case "end":
        try stream.write(summary.json)
        return summary
      case "error":
        throw Failure.phone(frame["error"] as? String ?? "error")
      default:
        throw Failure.protocolError("frame type \(frame["type"] ?? "missing")")
      }
    }
  }
}

/// Length-prefixed JSON frames over a connected socket.
public final class FrameStream {
  public let fd: Int32

  public init(fd: Int32, timeout: TimeInterval = 120) {
    self.fd = fd
    var tv = timeval(tv_sec: Int(timeout), tv_usec: 0)
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
    var on: Int32 = 1
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
  }

  deinit { close(fd) }

  public func write(_ object: [String: Any]) throws {
    let body = try JSONSerialization.data(withJSONObject: object)
    var length = UInt32(body.count).bigEndian
    try Self.writeAll(fd, Data(bytes: &length, count: 4) + body)
  }

  public func read() throws -> [String: Any] {
    let header = try Self.readExactly(fd, 4)
    let length = Int(header.withUnsafeBytes { $0.loadUnaligned(as: UInt32.self).bigEndian })
    guard length > 0, length <= USB.maxFrame else {
      throw USB.Failure.protocolError("frame of \(length) bytes")
    }
    let body = try Self.readExactly(fd, length)
    guard let object = try JSONSerialization.jsonObject(with: body) as? [String: Any] else {
      throw USB.Failure.protocolError("a frame that is not a JSON object")
    }
    return object
  }

  static func writeAll(_ fd: Int32, _ data: Data) throws {
    try data.withUnsafeBytes { raw in
      var offset = 0
      while offset < raw.count {
        let n = Darwin.write(fd, raw.baseAddress! + offset, raw.count - offset)
        guard n > 0 else { throw USB.Failure.protocolError("write failed (\(errno))") }
        offset += n
      }
    }
  }

  static func readExactly(_ fd: Int32, _ count: Int) throws -> Data {
    var data = Data(count: count)
    var offset = 0
    try data.withUnsafeMutableBytes { raw in
      while offset < count {
        let n = Darwin.read(fd, raw.baseAddress! + offset, count - offset)
        guard n > 0 else {
          throw USB.Failure.protocolError(n == 0 ? "the phone closed the connection" : "read failed (\(errno))")
        }
        offset += n
      }
    }
    return data
  }
}

/// A minimal client for macOS's usbmuxd (`/var/run/usbmuxd`, plist protocol).
public enum USBMux {
  public struct Device: Sendable {
    public let id: Int
    public let serial: String
  }

  static let path = "/var/run/usbmuxd"

  static func open() throws -> Int32 {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw USB.Failure.usbmuxd("no socket") }
    var addr = sockaddr_un()
    addr.sun_family = sa_family_t(AF_UNIX)
    withUnsafeMutableBytes(of: &addr.sun_path) { buffer in
      for (i, byte) in path.utf8.enumerated() { buffer[i] = byte }
    }
    let ok = withUnsafePointer(to: &addr) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
      }
    }
    guard ok == 0 else {
      close(fd)
      throw USB.Failure.usbmuxd("cannot reach \(path)")
    }
    return fd
  }

  static func send(_ fd: Int32, _ message: [String: Any]) throws {
    var dict = message
    dict["ClientVersionString"] = "health-graph"
    dict["ProgName"] = "health-graph"
    let body = try PropertyListSerialization.data(fromPropertyList: dict, format: .xml, options: 0)
    var header = [UInt32(16 + body.count), 1, 8, 1].map { $0.littleEndian }  // length, version, plist, tag
    try FrameStream.writeAll(fd, Data(bytes: &header, count: 16) + body)
  }

  static func receive(_ fd: Int32) throws -> [String: Any] {
    let header = try FrameStream.readExactly(fd, 16)
    let length = Int(header.withUnsafeBytes { $0.loadUnaligned(as: UInt32.self).littleEndian })
    guard length >= 16, length < 1 << 20 else { throw USB.Failure.usbmuxd("bad reply") }
    let body = try FrameStream.readExactly(fd, length - 16)
    guard let plist = try PropertyListSerialization.propertyList(from: body, format: nil) as? [String: Any]
    else { throw USB.Failure.usbmuxd("bad reply") }
    return plist
  }

  /// iPhones connected by cable (not over Wi-Fi).
  public static func devices() throws -> [Device] {
    let fd = try open()
    defer { close(fd) }
    try send(fd, ["MessageType": "ListDevices"])
    let reply = try receive(fd)
    return ((reply["DeviceList"] as? [[String: Any]]) ?? []).compactMap { entry in
      guard let props = entry["Properties"] as? [String: Any],
        props["ConnectionType"] as? String == "USB",
        let id = (entry["DeviceID"] as? Int) ?? (props["DeviceID"] as? Int)
      else { return nil }
      return Device(id: id, serial: props["SerialNumber"] as? String ?? "")
    }
  }

  /// A TCP stream to `port` on the phone's loopback, through the cable.
  public static func connect(device: Int, port: UInt16) throws -> Int32 {
    let fd = try open()
    do {
      try send(fd, ["MessageType": "Connect", "DeviceID": device, "PortNumber": Int(port.bigEndian)])
      let reply = try receive(fd)
      guard reply["MessageType"] as? String == "Result" else {
        throw USB.Failure.usbmuxd("unexpected reply")
      }
      switch reply["Number"] as? Int {
      case 0: return fd
      case 3: throw USB.Failure.refused
      case let n: throw USB.Failure.usbmuxd("connect failed (\(n ?? -1))")
      }
    } catch {
      close(fd)
      throw error
    }
  }
}
