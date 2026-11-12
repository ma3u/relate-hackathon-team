import Foundation
import HealthGraph
import Testing

@testable import HealthGraphReceiver

/// The USB protocol, with a fake phone on the other end of a socket pair
/// (usbmuxd only adds the cable in between).
@Suite("USB transfer", .serialized)
struct USBTests {
  /// The phone's side: checks the token, then sends `frames` and reads the summary.
  func fakePhone(_ fd: Int32, token: String, frames: [[String: Any]]) -> Task<[String: Any], Error> {
    let stream = FrameStream(fd: fd, timeout: 10)
    let payload = try! JSONSerialization.data(withJSONObject: frames)
    return Task.detached {
      let frames = try JSONSerialization.jsonObject(with: payload) as! [[String: Any]]
      let hello = try stream.read()
      guard hello["token"] as? String == token else {
        try stream.write(["type": "error", "error": "not the paired Mac"])
        return [:]
      }
      for frame in frames { try stream.write(frame) }
      return try stream.read()
    }
  }

  func pair() -> (Int32, Int32) {
    var fds: [Int32] = [0, 0]
    precondition(socketpair(AF_UNIX, SOCK_STREAM, 0, &fds) == 0)
    return (fds[0], fds[1])
  }

  @Test func reportsAndWearablesArriveLikeOverWiFi() async throws {
    let store = try tempDir().appendingPathComponent("health.rl")
    let bundle = try JSONSerialization.jsonObject(with: Data(contentsOf: golden)) as! [String: Any]
    let wear = try JSONSerialization.jsonObject(with: Data(contentsOf: wearables)) as! [String: Any]
    let (mac, phone) = pair()
    let answer = fakePhone(
      phone, token: "t0ken",
      frames: [
        ["type": "record", "report": "3f2a", "bundle": bundle],
        ["type": "record", "report": "3f2a", "bundle": bundle],  // sent again: replaces
        ["type": "wearables", "bundle": wear],
        ["type": "end"],
      ])
    let summary = try USB.pull(FrameStream(fd: mac, timeout: 10), token: "t0ken", store: store) { _ in }
    #expect(summary.reports == 2 && summary.stored == 14 && summary.weekly == 16)
    let reply = try await answer.value
    #expect(reply["stored"] as? Int == 14 && reply["weekly"] as? Int == 16)
    #expect(try HealthStore(path: store.path, readOnly: true).count("Observation") == 7 + 16)
  }

  @Test func aPhoneThatRefusesTheTokenStopsTheTransfer() async throws {
    let store = try tempDir().appendingPathComponent("health.rl")
    let (mac, phone) = pair()
    _ = fakePhone(phone, token: "the-real-one", frames: [])
    #expect(throws: USB.Failure.self) {
      try USB.pull(FrameStream(fd: mac, timeout: 10), token: "wrong", store: store) { _ in }
    }
  }

  @Test func framesRoundTrip() throws {
    let (a, b) = pair()
    let x = FrameStream(fd: a, timeout: 5)
    let y = FrameStream(fd: b, timeout: 5)
    try x.write(["type": "end", "n": 3, "text": "Körpergewicht"])
    let got = try y.read()
    #expect(got["type"] as? String == "end" && got["n"] as? Int == 3 && got["text"] as? String == "Körpergewicht")
  }

  /// usbmuxd answers on this Mac (the list may be empty without a phone on the cable).
  @Test func usbmuxdAnswers() throws {
    _ = try USBMux.devices()
  }
}
