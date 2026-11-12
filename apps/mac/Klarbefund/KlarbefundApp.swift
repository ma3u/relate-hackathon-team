import AppKit
import SwiftUI

@main
struct KlarbefundApp: App {
  @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

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
    #endif
  }

  /// Closing the window quits: the graph is sealed and Claude's access ends.
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

  func applicationWillTerminate(_ notification: Notification) {
    MainActor.assumeIsolated { AppModel.shared.stop() }
  }
}
