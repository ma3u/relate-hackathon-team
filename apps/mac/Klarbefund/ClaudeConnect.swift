import AppKit
import Foundation

/// Connects Claude Desktop with one click: builds a Claude Desktop extension
/// (.mcpb) around the bundled MCP helper and hands it to Claude, which asks the
/// person to install it. No terminal, no config files, no scripts.
enum ClaudeConnect {
  static let claudeBundleID = "com.anthropic.claudefordesktop"
  static var claudeApp: URL? { NSWorkspace.shared.urlForApplication(withBundleIdentifier: claudeBundleID) }
  static var helper: URL { Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/klarbefund-mcp") }

  /// The extension's version: the app's version and build (1.0.8), so Claude Desktop sees a new build as
  /// an update. Until build 8 every build said 1.0.0, and Claude kept running the helper it installed first.
  static var extensionVersion: String {
    let short = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "0"
    return "\(short).\(build)"
  }

  enum Failure: Error, CustomStringConvertible {
    case noClaude, noHelper, zip(Int32)
    var description: String {
      switch self {
      case .noClaude: return String(localized: "Claude Desktop is not installed. Get it at claude.ai/download, then click Connect again.")
      case .noHelper:
        return String(localized: "The Claude connector is missing from this copy of Klarbefund. Reinstall Klarbefund from TestFlight.")
      case .zip(let code): return String(localized: "Could not package the Claude extension (ditto \(Int(code))).")
      }
    }
  }

  static func install() throws { try open(try makeExtension()) }

  /// Hands a finished extension file to Claude Desktop, which asks the person to install it.
  static func open(_ mcpb: URL) throws {
    guard let claude = claudeApp else { throw Failure.noClaude }
    let config = NSWorkspace.OpenConfiguration()
    config.activates = true
    NSWorkspace.shared.open([mcpb], withApplicationAt: claude, configuration: config)
  }

  /// The extension: manifest.json, the helper binary and an icon, zipped with the
  /// manifest at the root. Each call writes its own file, complete before Claude sees it, and never
  /// touches one handed over before: on Nov 16, 2026 a second click rewrote the file while Claude
  /// read the first ("truncated"), then deleted it ("Extension file not found"). Files older than an
  /// hour are cleared.
  static func makeExtension(icon: Data? = nil) throws -> URL {
    let fm = FileManager.default
    guard fm.isExecutableFile(atPath: helper.path) else { throw Failure.noHelper }
    let base = fm.temporaryDirectory.appendingPathComponent("claude-extension", isDirectory: true)
    try fm.createDirectory(at: base, withIntermediateDirectories: true)
    for old in (try? fm.contentsOfDirectory(at: base, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] {
      let when = (try? old.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
      if Date().timeIntervalSince(when) > 3600 { try? fm.removeItem(at: old) }
    }
    try? fm.removeItem(at: fm.temporaryDirectory.appendingPathComponent("Klarbefund Health Graph.mcpb"))  // before build 10
    let run = base.appendingPathComponent("\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))", isDirectory: true)
    let root = run.appendingPathComponent("klarbefund-health", isDirectory: true)
    try fm.createDirectory(at: root.appendingPathComponent("server"), withIntermediateDirectories: true)
    try fm.copyItem(at: helper, to: root.appendingPathComponent("server/klarbefund-mcp"))
    // The icon is drawn on the main thread (AppKit); off it, the caller passes it in.
    if let icon = icon ?? (Thread.isMainThread ? MainActor.assumeIsolated { NSApp.applicationIconImage?.pngData(size: 512) } : nil) {
      try icon.write(to: root.appendingPathComponent("icon.png"))
    }
    let manifest: [String: Any] = [
      "manifest_version": "0.2",
      "name": MCPCatalog.serverName,
      "display_name": MCPCatalog.serverTitle,
      "version": extensionVersion,
      "description": "Your lab reports and Apple Watch data from Klarbefund, as a local Neo4j Relate graph. Read-only, on this Mac.",
      "long_description": "Klarbefund for Mac keeps your health graph on your own Mac. This extension lets Claude read it, read-only, while Klarbefund for Mac is open. Nothing is uploaded to a cloud by Klarbefund; only the rows Claude asks for go into your conversation.",
      "author": ["name": "Matthias Buchhorn", "url": "https://github.com/ma3u/relate-hackathon-team"],
      "homepage": "https://ma3u.github.io/relate-hackathon-team/",
      "icon": "icon.png",
      "server": [
        "type": "binary",
        "entry_point": "server/klarbefund-mcp",
        "mcp_config": ["command": "${__dirname}/server/klarbefund-mcp", "args": [String](), "env": [String: String]()],
      ],
      "tools": MCPCatalog.tools.map { ["name": $0.name, "description": $0.summary] },
      // The same catalog the helper serves through prompts/list and prompts/get.
      "prompts": MCPCatalog.prompts.map { p -> [String: Any] in
        [
          "name": p.name, "description": p.description,
          "arguments": p.arguments.map(\.name),
          "text": MCPCatalog.render(p, arguments: [:]),
        ]
      },
      "keywords": ["health", "neo4j", "relate", "graph", "fhir", "loinc"],
      "license": "Apache-2.0",
      "compatibility": ["platforms": ["darwin"]],
    ]
    let data = try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
    try data.write(to: root.appendingPathComponent("manifest.json"))

    let out = run.appendingPathComponent("Klarbefund Health Graph.mcpb")
    let partial = run.appendingPathComponent("extension.partial")
    let ditto = Process()
    ditto.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
    ditto.arguments = ["-c", "-k", "--norsrc", "--noextattr", "--noqtn", root.path, partial.path]
    try ditto.run()
    ditto.waitUntilExit()
    guard ditto.terminationStatus == 0 else { throw Failure.zip(ditto.terminationStatus) }
    try fm.moveItem(at: partial, to: out)  // whole, in one step
    try? fm.removeItem(at: root)
    return out
  }

  /// For people who prefer to add it by hand (Claude Desktop → Settings →
  /// Developer → Edit Config).
  static var manualConfig: String {
    """
    {
      "mcpServers": {
        "klarbefund-health": {
          "command": "\(helper.path)"
        }
      }
    }
    """
  }
}

extension NSImage {
  func pngData(size: Int) -> Data? {
    let rep = NSBitmapImageRep(
      bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4,
      hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
    guard let rep else { return nil }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    draw(in: NSRect(x: 0, y: 0, width: size, height: size))
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])
  }
}
