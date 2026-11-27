import HealthGraph
import SwiftUI
import WebKit

/// The 3D view of the health graph (scripts/graph3d.html, bundled), in its own window. The page
/// gets its data from Claude's read-only snapshot, built by the HealthGraph library the way
/// scripts/graph3d.py builds it for the vault; "Save to my graph" hands a protocol's answers back
/// to the app (window.webkit.messageHandlers.klarbefund), which stores them in the graph it owns.
/// The page loads 3d-force-graph from jsDelivr; nothing of the graph leaves the Mac.
struct Graph3DView: NSViewRepresentable {
  func makeCoordinator() -> Coordinator { Coordinator() }

  func makeNSView(context: Context) -> WKWebView {
    let content = WKUserContentController()
    content.addScriptMessageHandler(context.coordinator, contentWorld: .page, name: "klarbefund")
    content.addUserScript(WKUserScript(
      source: "window.GRAPH3D_SAVE = {native: true};", injectionTime: .atDocumentStart, forMainFrameOnly: true))
    let config = WKWebViewConfiguration()
    config.userContentController = content
    config.websiteDataStore = .nonPersistent()  // nothing of the page is kept on disk
    let web = WKWebView(frame: .zero, configuration: config)
    web.uiDelegate = context.coordinator  // a link that opens a new window (target=_blank) goes to the browser
    load(into: web)
    return web
  }

  func updateNSView(_ web: WKWebView, context: Context) {}

  /// Builds the page off the main thread and loads it.
  private func load(into web: WKWebView) {
    Task.detached(priority: .userInitiated) {
      let html = Self.page()
      await MainActor.run { _ = web.loadHTMLString(html, baseURL: nil) }
    }
  }

  nonisolated static func page() -> String {
    guard let url = Bundle.main.url(forResource: "graph3d", withExtension: "html"),
      let template = try? String(contentsOf: url, encoding: .utf8)
    else { return message(String(localized: "The 3D view is missing from this build of Klarbefund.")) }
    guard let snap = Paths.snapshot, FileManager.default.fileExists(atPath: snap.path) else {
      return message(String(localized: "Your health graph is not open yet. Send your reports from the iPhone first."))
    }
    do {
      let day = ISO8601DateFormatter.string(from: Date(), timeZone: .current, formatOptions: [.withFullDate])
      return try Snapshot.read(snap) { try $0.graph3DPage(template: template, today: day) }
    } catch {
      return message(String(localized: "Klarbefund could not read your health graph for the 3D view: \(String(describing: error))"))
    }
  }

  nonisolated static func message(_ text: String) -> String {
    let safe = text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
    return "<html><body style=\"background:#0b0d11;color:#e8e8e8;font:15px -apple-system;padding:40px\">\(safe)</body></html>"
  }

  final class Coordinator: NSObject, WKScriptMessageHandlerWithReply, WKUIDelegate {
    /// The page's outbound links (the publisher's page, PubMed, a guideline's PDF at its page) open in the
    /// default browser; only https, and the page itself never navigates away.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
      if let url = navigationAction.request.url, url.scheme == "https" { NSWorkspace.shared.open(url) }
      return nil
    }

    @MainActor func userContentController(
      _ controller: WKUserContentController, didReceive message: WKScriptMessage
    ) async -> (Any?, String?) {
      guard let body = message.body as? [String: Any], let id = body["protocol"] as? String,
        let answers = body["answers"] as? [String: Any]
      else { return (["ok": false, "error": "not a protocol's answers"], nil) }
      return (AppModel.shared.storeFromView(id, answers), nil)
    }
  }
}
