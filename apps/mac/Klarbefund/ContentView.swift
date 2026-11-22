import AppKit
import SwiftUI

/// Set while rendering the docs screenshot: ImageRenderer draws no AppKit-backed
/// controls, so small buttons and links are drawn as plain images and text then.
@MainActor var renderingForDocs = false

/// Set by the debug `--letter-render` run: the main window then never opens or seals the real graph.
@MainActor var skipGraph = false

/// One window, three steps: pair the iPhone, see the graph, connect an AI (Claude, ChatGPT, Gemini or a local model).
struct ContentView: View {
  @ObservedObject var model: AppModel
  @State private var showManual = false
  @State private var showCapabilities = false
  @State private var skillMessage: String?
  @State private var client: AIClient

  init(model: AppModel, client: AIClient = .claude) {
    self.model = model
    _client = State(initialValue: client)
  }
  @State private var localMessage: String?
  @Environment(\.openWindow) private var openWindow

  var body: some View {
    VStack(alignment: .leading, spacing: 18) {
      header
      if let problem = model.problem {
        Label(problem, systemImage: "exclamationmark.triangle.fill")
          .foregroundStyle(.red).textSelection(.enabled)
      }
      HStack(alignment: .top, spacing: 18) {
        Step(number: 1, title: "Pair your iPhone", symbol: "iphone.gen3") { pairing }
        Step(number: 2, title: "Your health graph", symbol: "point.3.connected.trianglepath.dotted") { graph }
        Step(number: 3, title: "Ask your AI", symbol: "bubble.left.and.text.bubble.right") { ai }
      }
      footer
    }
    .padding(24)
    .frame(minWidth: 1020, minHeight: 640)
  }

  private var header: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text("Klarbefund for Mac").font(.largeTitle.bold())
      Text("Your lab reports and Apple Watch data in one health graph, on this Mac. Encrypted, local, no cloud.")
        .foregroundStyle(.secondary)
    }
  }

  // ── 1 ──
  @ViewBuilder private var pairing: some View {
    if let qr = model.qr {
      Image(nsImage: qr).interpolation(.none).resizable().frame(width: 200, height: 200)
        .padding(8).background(.white, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityLabel("Pairing QR code")
    } else {
      ProgressView().frame(width: 200, height: 200)
    }
    Numbered(items: [
      "On your iPhone, open **Klarbefund**.",
      "More (…) → **Export to my Mac (Relate)**.",
      "Scan this code, then tap **Send everything now**.",
    ])
    Text("iPhone and Mac need the same Wi-Fi. The connection is encrypted and pinned to this Mac (\(model.address)).")
      .font(.caption).foregroundStyle(.secondary)
    if let last = model.lastReceived {
      Label("Data received \(last.formatted(.relative(presentation: .named)))", systemImage: "checkmark.circle.fill")
        .foregroundStyle(.green)
    } else {
      Label("Waiting for your iPhone…", systemImage: "antenna.radiowaves.left.and.right").foregroundStyle(.secondary)
    }
  }

  // ── 2 ──
  @ViewBuilder private var graph: some View {
    Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 10) {
      CountRow(value: model.counts.reports, label: "lab reports")
      CountRow(value: model.counts.values, label: "lab values")
      CountRow(value: model.counts.weeks, label: "Apple Watch weeks")
      CountRow(value: model.counts.codes, label: "LOINC codes")
      CountRow(value: model.counts.ranges, label: "reference ranges")
    }
    Divider()
    Label("Sealed with AES-256 while Klarbefund is closed; the key stays in this Mac's keychain.", systemImage: "lock.fill")
      .font(.callout)
    Label("Neo4j Relate, one file, inside this app's sandbox. Nothing is uploaded.", systemImage: "internaldrive")
      .font(.callout)
    if renderingForDocs {  // ImageRenderer draws no AppKit button: the same look, drawn
      Label("Open 3D view", systemImage: "cube.transparent").frame(maxWidth: .infinity)
        .padding(.vertical, 7).background(.quaternary, in: RoundedRectangle(cornerRadius: 7))
    } else {
      Button { openWindow(id: "graph3d") } label: {
        Label("Open 3D view", systemImage: "cube.transparent").frame(maxWidth: .infinity)
      }
      .controlSize(.large)
      .disabled(model.counts.values == 0 && model.counts.weeks == 0)
      .help("Your risks, values, evidence and anamnesis as an interactive 3D graph, on this Mac.")
    }
    HStack(spacing: 10) {
      if renderingForDocs {  // drawn, as above
        ForEach([("Doctor's letter", "doc.text"), ("Anamnesis", "list.bullet.clipboard")], id: \.0) { title, symbol in
          Label(LocalizedStringKey(title), systemImage: symbol).frame(maxWidth: .infinity)
            .padding(.vertical, 7).background(.quaternary, in: RoundedRectangle(cornerRadius: 7))
        }
      } else {
        Button { openWindow(id: "doctor-letter") } label: {
          Label("Doctor's letter", systemImage: "doc.text").frame(maxWidth: .infinity)
        }
        .controlSize(.large)
        .disabled(model.counts.values == 0 && model.counts.weeks == 0)
        .help("Your latest lab tests, trends, Apple Watch vitals, sport and anamnesis on one A4 letter for your GP or a specialist, in German or English.")
        Button { openWindow(id: "anamnesis") } label: {
          Label("Anamnesis", systemImage: "list.bullet.clipboard").frame(maxWidth: .infinity)
        }
        .controlSize(.large)
        .disabled(model.counts.values == 0 && model.counts.weeks == 0)
        .help("Answer what your data cannot tell, and the validated questionnaires, here on this Mac.")
      }
    }
    if !model.activity.isEmpty {
      DisclosureGroup("Activity") {
        ScrollView {
          VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(model.activity.enumerated()), id: \.offset) { Text($0.element).font(.caption.monospaced()) }
          }.frame(maxWidth: .infinity, alignment: .leading)
        }.frame(height: 90)
      }
    }
  }

  // ── 3 ──
  private var setup: AISetup { AISetup(helper: ClaudeConnect.helper.path) }

  /// Step 3 scrolls: ChatGPT's and Gemini's setups are taller than Claude's one button. ImageRenderer
  /// draws no scroll view, so the docs render lays the content out directly.
  @ViewBuilder private var ai: some View {
    if renderingForDocs {
      aiContent
    } else {
      ScrollView(.vertical) {
        VStack(alignment: .leading, spacing: 12) { aiContent }.frame(maxWidth: .infinity, alignment: .leading)
      }
    }
  }

  @ViewBuilder private var aiContent: some View {
    if renderingForDocs {  // ImageRenderer draws no segmented control
      Text(AIClient.allCases.map { loc($0.title) }.joined(separator: " · ")).font(.callout.weight(.semibold))
    } else {
      Picker("AI", selection: $client) {
        ForEach(AIClient.allCases) { Text(loc($0.title)).tag($0) }
      }
      .pickerStyle(.segmented).labelsHidden()
    }
    switch client {
    case .claude: claude
    case .chatgpt: chatgpt
    case .gemini: gemini
    case .local: local
    }
    Label(loc(client.privacy), systemImage: client == .local ? "lock.laptopcomputer" : "cloud")
      .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
    Text("Then ask, for example:").font(.callout.weight(.semibold)).padding(.top, 4)
    ForEach(MCPCatalog.prompts.filter { $0.group == .risks }.prefix(3), id: \.name) { Ask(loc($0.ask)) }
    let catalog = Label(
      "What it can do here (\(MCPCatalog.prompts.count) prompts, \(MCPCatalog.guides.count) guides)",
      systemImage: "list.bullet.rectangle")  // the prompts and guides stay English: they are sent to the AI
    if renderingForDocs {
      catalog.font(.callout).foregroundStyle(Color.accentColor)
    } else {
      Button { showCapabilities = true } label: { catalog }
        .buttonStyle(.link).font(.callout)
        .sheet(isPresented: $showCapabilities) { MCPCapabilitiesView() }
    }
  }

  @ViewBuilder private var chatgpt: some View {
    Text("ChatGPT for Mac and Codex CLI share one setup. ChatGPT in the browser cannot reach your Mac.")
    Numbered(items: [
      "ChatGPT → **Settings → MCP servers → Add server**.",
      "Choose **STDIO**, name it **\(AISetup.serverName)**, command:",
    ])
    Code(setup.helper)
    Text("Save, then Restart ChatGPT. Or in Terminal, for Codex CLI:").font(.callout)
    Code(setup.codexCommand)
    DisclosureGroup("In ~/.codex/config.toml") { Code(setup.codexToml) }.font(.callout)
  }

  @ViewBuilder private var gemini: some View {
    Text("Gemini CLI, in Terminal:")
    Code(setup.geminiCommand)
    Numbered(items: [
      "Start **gemini** in a folder you trust: in an untrusted folder Gemini CLI switches MCP servers off.",
      "Type **/mcp**: \(AISetup.serverName) shows as connected.",
    ])
    DisclosureGroup("In ~/.gemini/settings.json") { Code(setup.mcpServersJson) }.font(.callout)
  }

  @ViewBuilder private var local: some View {
    Text("LM Studio (0.3.17 or later) runs the model on this Mac. Pick a model that supports tool use.")
    if renderingForDocs {
      Label("Add to LM Studio", systemImage: "plus.app").frame(maxWidth: .infinity)
        .padding(.vertical, 7).background(.quaternary, in: RoundedRectangle(cornerRadius: 7))
    } else {
      Button {
        guard let link = setup.lmStudioLink, NSWorkspace.shared.urlForApplication(toOpen: link) != nil else {
          localMessage = String(localized: "LM Studio is not installed. Get it at lmstudio.ai, open it once, then click again.")
          return
        }
        localMessage = String(localized: "LM Studio asks to add \(AISetup.serverName): confirm, then start a chat with a tool-use model.")
        NSWorkspace.shared.open(link)
      } label: {
        Label("Add to LM Studio", systemImage: "plus.app").frame(maxWidth: .infinity)
      }
      .controlSize(.large)
    }
    if let localMessage { Text(localMessage).font(.callout).foregroundStyle(.secondary) }
    DisclosureGroup("By hand: LM Studio → Program → Install → Edit mcp.json") { Code(setup.mcpServersJson) }
      .font(.callout)
    Text("Ollama has no MCP support of its own: an MCP client in front of it takes the same JSON.")
      .font(.caption).foregroundStyle(.secondary)
  }

  @ViewBuilder private var claude: some View {
    Text("Claude Desktop can read your graph, read-only, while Klarbefund is open.")
    Button {
      model.connectClaude()
    } label: {
      Label(model.connecting ? LocalizedStringKey("Preparing the extension…") : LocalizedStringKey("Connect Claude Desktop"),
            systemImage: model.connecting ? "hourglass" : "link").frame(maxWidth: .infinity)
    }
    .controlSize(.large).buttonStyle(.borderedProminent)
    .disabled(model.connecting)
    if model.claudeMessage == nil && model.extensionOutdated && !renderingForDocs {
      Label("Klarbefund was updated. If you connected Claude before, click Connect again so Claude gets the new tools (version \(ClaudeConnect.extensionVersion)). Your health graph is not affected.",
        systemImage: "arrow.triangle.2.circlepath")
        .font(.callout).foregroundStyle(.secondary)
    }
    if let msg = model.claudeMessage {
      Text(msg).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
    }
    if renderingForDocs {
      Label("Add the Klarbefund skill to Claude", systemImage: "square.and.arrow.down")
        .font(.callout).foregroundStyle(Color.accentColor)
    } else {
      Button { skillMessage = SkillExport.save() } label: {
        Label("Add the Klarbefund skill to Claude", systemImage: "square.and.arrow.down")
      }
      .buttonStyle(.link).font(.callout)
      .help("Saves the anamnesis method as a skill (no health data) for Claude's Customize → Skills → Upload.")
      if let skillMessage, !skillMessage.isEmpty {
        Text(skillMessage).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
      }
    }
    DisclosureGroup("Set it up by hand", isExpanded: $showManual) {
      Text("Claude Desktop → Settings → Developer → Edit Config, add:").font(.caption)
      Text(ClaudeConnect.manualConfig).font(.caption.monospaced()).textSelection(.enabled)
        .padding(6).background(.quaternary, in: RoundedRectangle(cornerRadius: 6))
      Button("Copy") { copy(ClaudeConnect.manualConfig) }.controlSize(.small)
    }.font(.callout)
  }

  private var footer: some View {
    HStack {
      Text("Not a medical device: help to understand your data and prepare questions for your doctor.")
      Spacer()
      if renderingForDocs {
        Text("How it works").foregroundStyle(Color.accentColor)
      } else {
        Link("How it works", destination: URL(string: "https://ma3u.github.io/relate-hackathon-team/")!)
      }
    }
    .font(.caption).foregroundStyle(.secondary)
  }
}

private struct Step<Content: View>: View {
  let number: Int, title: LocalizedStringKey, symbol: String
  @ViewBuilder var content: Content
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 10) {
        Text("\(number)").font(.headline).frame(width: 28, height: 28)
          .background(Color.accentColor, in: Circle()).foregroundStyle(.white)
        Label(title, systemImage: symbol).font(.title3.weight(.semibold))
      }
      content
      Spacer(minLength: 0)
    }
    .padding(18)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16))
  }
}

private struct Numbered: View {
  let items: [String]
  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      ForEach(Array(items.enumerated()), id: \.offset) { i, s in
        HStack(alignment: .firstTextBaseline, spacing: 6) {
          Text("\(i + 1).").foregroundStyle(.secondary)
          Text(LocalizedStringKey(s)).fixedSize(horizontal: false, vertical: true)  // wraps, never "…"
        }
      }
    }
  }
}

private struct CountRow: View {
  let value: Int, label: LocalizedStringKey
  var body: some View {
    GridRow {
      Text(value.formatted()).font(.title2.bold().monospacedDigit()).gridColumnAlignment(.trailing)
      Text(label).foregroundStyle(.secondary)
    }
  }
}

/// A command or config to copy: monospaced, selectable, with a copy button.
private struct Code: View {
  let text: String
  init(_ text: String) { self.text = text }
  var body: some View {
    HStack(alignment: .top, spacing: 6) {
      Text(text).font(.caption.monospaced()).textSelection(.enabled)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      if !renderingForDocs {
        Button { copy(text) } label: { Image(systemName: "doc.on.doc") }
          .buttonStyle(.borderless).help("Copy")
      }
    }
    .padding(6).background(.quaternary, in: RoundedRectangle(cornerRadius: 6))
  }
}

private struct Ask: View {
  let text: String
  init(_ text: String) { self.text = text }
  var body: some View {
    HStack {
      Text("“\(text)”").font(.callout)
      Spacer()
      if renderingForDocs {
        Image(systemName: "doc.on.doc").foregroundStyle(Color.accentColor)
      } else {
        Button { copy(text) } label: { Image(systemName: "doc.on.doc") }
          .buttonStyle(.borderless).help("Copy")
      }
    }
  }
}

func copy(_ s: String) {
  NSPasteboard.general.clearContents()
  NSPasteboard.general.setString(s, forType: .string)
}
