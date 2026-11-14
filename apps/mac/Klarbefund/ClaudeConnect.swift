import AppKit
import Foundation

/// Connects Claude Desktop with one click: builds a Claude Desktop extension
/// (.mcpb) around the bundled MCP helper and hands it to Claude, which asks the
/// person to install it. No terminal, no config files, no scripts.
enum ClaudeConnect {
  static let claudeBundleID = "com.anthropic.claudefordesktop"
  static var claudeApp: URL? { NSWorkspace.shared.urlForApplication(withBundleIdentifier: claudeBundleID) }
  static var helper: URL { Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/klarbefund-mcp") }

  enum Failure: Error, CustomStringConvertible {
    case noClaude, noHelper, zip(Int32)
    var description: String {
      switch self {
      case .noClaude: return "Claude Desktop is not installed. Get it at claude.ai/download, then click Connect again."
      case .noHelper: return "The Claude connector is missing from this copy of Klarbefund. Reinstall Klarbefund from TestFlight."
      case .zip(let code): return "Could not package the Claude extension (ditto \(code))."
      }
    }
  }

  static func install() throws {
    guard let claude = claudeApp else { throw Failure.noClaude }
    let mcpb = try makeExtension()
    let config = NSWorkspace.OpenConfiguration()
    config.activates = true
    NSWorkspace.shared.open([mcpb], withApplicationAt: claude, configuration: config)
  }

  /// The extension: manifest.json, the helper binary and an icon, zipped with the
  /// manifest at the root.
  static func makeExtension() throws -> URL {
    let fm = FileManager.default
    guard fm.isExecutableFile(atPath: helper.path) else { throw Failure.noHelper }
    let root = fm.temporaryDirectory.appendingPathComponent("klarbefund-health", isDirectory: true)
    try? fm.removeItem(at: root)
    try fm.createDirectory(at: root.appendingPathComponent("server"), withIntermediateDirectories: true)
    try fm.copyItem(at: helper, to: root.appendingPathComponent("server/klarbefund-mcp"))
    if let icon = NSApp.applicationIconImage?.pngData(size: 512) {
      try icon.write(to: root.appendingPathComponent("icon.png"))
    }
    let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    let manifest: [String: Any] = [
      "manifest_version": "0.2",
      "name": MCPCatalog.serverName,
      "display_name": MCPCatalog.serverTitle,
      "version": version + ".0",
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
      "tools": [
        ["name": "get_schema", "description": "Labels and relationships in your health graph, with counts."],
        ["name": "read_cypher", "description": "One read-only Cypher query against your health graph."],
      ],
      // The same catalog the helper serves through prompts/list and prompts/get.
      "prompts": MCPCatalog.prompts.map { p -> [String: Any] in
        [
          "name": p.name, "description": p.description,
          "arguments": p.arguments.map(\.name),
          "text": MCPCatalog.render(p, arguments: [:]),
        ]
      },
      "keywords": ["health", "neo4j", "relate", "graph", "fhir", "loinc"],
      "license": "MIT",
      "compatibility": ["platforms": ["darwin"]],
    ]
    let data = try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
    try data.write(to: root.appendingPathComponent("manifest.json"))

    let out = fm.temporaryDirectory.appendingPathComponent("Klarbefund Health Graph.mcpb")
    try? fm.removeItem(at: out)
    let ditto = Process()
    ditto.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
    ditto.arguments = ["-c", "-k", "--norsrc", "--noextattr", "--noqtn", root.path, out.path]
    try ditto.run()
    ditto.waitUntilExit()
    guard ditto.terminationStatus == 0 else { throw Failure.zip(ditto.terminationStatus) }
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
