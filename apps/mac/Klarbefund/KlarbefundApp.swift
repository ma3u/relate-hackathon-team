import AppKit
import HealthGraphReceiver
import SwiftUI

@main
struct KlarbefundApp: App {
  @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

  init() {
    #if DEBUG
      Self.renderForDocsIfAsked()
    #endif
  }

  #if DEBUG
    /// `--screenshot PATH`: the window with fictional demo data (no token, a
    /// documentation address), for the docs. Runs in `init`, before any window
    /// exists: a window's `onAppear` opens and unseals the real graph, and a
    /// documentation render must never share a process with that.
    ///
    /// `--size WxH` (points, rendered at 2x), `--light`, `--claude`: App Store
    /// variants. `--counts R,V,W,C,RA`, `--waiting` (nothing received yet) and
    /// `--received-ago SECONDS`: the states of one fictional run, for the
    /// docs' pairing animation.
    @MainActor private static func renderForDocsIfAsked() {
      let args = CommandLine.arguments
      guard let i = args.firstIndex(of: "--screenshot"), i + 1 < args.count else { return }
      renderingForDocs = true
      let demo = AppModel()
      demo.address = "192.0.2.10"
      demo.counts = GraphCounts(reports: 7, values: 52, weeks: 120, codes: 123, ranges: 173)
      demo.lastReceived = Date().addingTimeInterval(-120)
      if let png = QRCode("klarbefund://relate?demo=fictional-pairing-for-the-docs")?.png(scale: 10, border: 2) {
        demo.qr = NSImage(data: png)
      }
      var w: CGFloat = 1020, h: CGFloat = 672
      if let s = args.firstIndex(of: "--size"), s + 1 < args.count {
        let p = args[s + 1].split(separator: "x").compactMap { Double($0) }
        if p.count == 2 { w = p[0]; h = p[1] }
      }
      if let c = args.firstIndex(of: "--counts"), c + 1 < args.count {
        let n = args[c + 1].split(separator: ",").compactMap { Int($0) }
        if n.count == 5 {
          demo.counts = GraphCounts(reports: n[0], values: n[1], weeks: n[2], codes: n[3], ranges: n[4])
        }
      }
      if args.contains("--waiting") { demo.lastReceived = nil }
      if let s = args.firstIndex(of: "--received-ago"), s + 1 < args.count, let secs = Double(args[s + 1]) {
        demo.lastReceived = Date().addingTimeInterval(-secs)
      }
      if args.contains("--claude") {
        demo.claudeMessage = "Claude Desktop is asking to install “Klarbefund Health Graph”. Click Install, then start a new chat."
      }
      let view = ContentView(model: demo).frame(width: w, height: h)
        .background(Color(nsColor: .windowBackgroundColor))
        .environment(\.colorScheme, args.contains("--light") ? .light : .dark)
      let renderer = ImageRenderer(content: view)
      renderer.scale = 2
      if let cg = renderer.cgImage {
        let rep = NSBitmapImageRep(cgImage: cg)
        try? rep.representation(using: .png, properties: [:])?
          .write(to: URL(fileURLWithPath: args[i + 1]))
      }
      exit(0)
    }
  #endif

  var body: some Scene {
    Window("Klarbefund", id: "main") {
      ContentView(model: AppModel.shared)
        .onAppear { AppModel.shared.start() }
    }
    .windowResizability(.contentMinSize)
  }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
  func applicationDidFinishLaunching(_ notification: Notification) {
    #if DEBUG
      // `--write-extension`: build the Claude extension, print its path and quit (for checks).
      if CommandLine.arguments.contains("--write-extension") {
        do { print(try ClaudeConnect.makeExtension().path) } catch { print("error: \(error)") }
        exit(0)
      }
      // `--tls-selftest`: a throwaway identity and store in the sandbox's temp
      // folder, one pinned HTTPS request, then quit. Proves the keychain and
      // Network-framework TLS path of a signed build without touching the graph.
      if CommandLine.arguments.contains("--tls-selftest") {
        Task.detached {
          print(await TLSSelfTest.run())
          exit(0)
        }
        return
      }
    #endif
  }

  /// Closing the window quits: the graph is sealed and Claude's access ends.
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

  func applicationWillTerminate(_ notification: Notification) {
    MainActor.assumeIsolated { AppModel.shared.stop() }
  }
}
