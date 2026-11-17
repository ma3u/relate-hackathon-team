import Foundation

/// The AI apps that can read the health graph through the bundled MCP helper, and how each is set up.
///
/// Every one of them starts the same helper on this Mac (stdio, read-only, except the answers it hands
/// to the app's Inbox). What differs is where the model runs, and so where the rows it reads go:
/// Claude, ChatGPT and Gemini run in their makers' clouds; a local model keeps everything on the Mac.
///
/// As of November 2026 (checked against the makers' docs):
/// - ChatGPT: the desktop app and Codex CLI share `~/.codex/config.toml` (`[mcp_servers.<name>]`,
///   `command`); the app adds a local server under Settings → MCP servers → Add server → STDIO.
///   ChatGPT in the browser cannot reach a server on the Mac.
/// - Gemini: Gemini CLI, `gemini mcp add -s user <name> <command>` into `~/.gemini/settings.json`.
/// - Local: LM Studio (0.3.17 and later) is an MCP host and takes `lmstudio://add_mcp?name=…&config=…`
///   with the server entry as base64 JSON; Ollama has no MCP support of its own.
public enum AIClient: String, CaseIterable, Identifiable, Sendable {
  case claude, chatgpt, gemini, local

  public var id: String { rawValue }

  public var title: String {
    switch self {
    case .claude: return "Claude"
    case .chatgpt: return "ChatGPT"
    case .gemini: return "Gemini"
    case .local: return "Local model"
    }
  }

  /// Where the rows the model reads end up: said plainly, next to every setup.
  public var privacy: String {
    switch self {
    case .claude:
      return "The model runs at Anthropic: the rows Claude reads from your graph go into your conversation there."
    case .chatgpt:
      return "The model runs at OpenAI: the rows ChatGPT reads from your graph go into your conversation there."
    case .gemini:
      return "The model runs at Google: the rows Gemini reads from your graph go into your conversation there."
    case .local:
      return "The model runs on this Mac: nothing from your graph leaves it."
    }
  }
}

/// The setup texts for one helper path. Pure, so they can be checked outside the app.
public struct AISetup: Sendable {
  public static let serverName = "klarbefund-health"
  public let helper: String

  public init(helper: String) { self.helper = helper }

  /// A path in single quotes for zsh/bash, safe with spaces.
  var quoted: String { "'" + helper.replacingOccurrences(of: "'", with: "'\\''") + "'" }

  /// JSON string literal for the path.
  var jsonPath: String {
    let data = try? JSONSerialization.data(withJSONObject: [helper], options: [.withoutEscapingSlashes])
    let array = data.flatMap { String(data: $0, encoding: .utf8) } ?? "[\"\(helper)\"]"
    return String(array.dropFirst().dropLast())
  }

  // ── ChatGPT (desktop app and Codex CLI share one configuration) ──
  public var codexCommand: String { "codex mcp add \(Self.serverName) -- \(quoted)" }
  public var codexToml: String {
    """
    [mcp_servers.\(Self.serverName)]
    command = \(jsonPath)
    """
  }

  // ── Gemini CLI ──
  public var geminiCommand: String { "gemini mcp add -s user \(Self.serverName) \(quoted)" }

  /// The mcpServers block Claude Desktop, Gemini CLI, LM Studio and most other MCP clients read.
  public var mcpServersJson: String {
    """
    {
      "mcpServers": {
        "\(Self.serverName)": {
          "command": \(jsonPath)
        }
      }
    }
    """
  }

  // ── LM Studio ──
  /// "Add to LM Studio": the server entry (without its name) as base64 JSON, as LM Studio's link generator makes it.
  public var lmStudioLink: URL? {
    let entry = (try? JSONSerialization.data(withJSONObject: ["command": helper], options: [.withoutEscapingSlashes])) ?? Data()
    // "+", "/" and "=" in base64 are data, not query syntax: escaped, as LM Studio's own links send "=" as %3D.
    let config = entry.base64EncodedString().addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    return URL(string: "lmstudio://add_mcp?name=\(Self.serverName)&config=\(config)")
  }
}
