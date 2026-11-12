import AppKit
import SwiftUI

/// Set while rendering the docs screenshot: ImageRenderer draws no AppKit-backed
/// controls, so small buttons and links are drawn as plain images and text then.
@MainActor var renderingForDocs = false

/// One window, three steps: pair the iPhone, see the graph, connect Claude.
struct ContentView: View {
  @ObservedObject var model: AppModel
  @State private var showManual = false

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
        Step(number: 3, title: "Ask Claude", symbol: "bubble.left.and.text.bubble.right") { claude }
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
      "Menu → **Export to my Mac (Relate)**.",
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
  @ViewBuilder private var claude: some View {
    Text("Claude Desktop can read your graph, read-only, while Klarbefund is open.")
    Button {
      model.connectClaude()
    } label: {
      Label("Connect Claude Desktop", systemImage: "link").frame(maxWidth: .infinity)
    }
    .controlSize(.large).buttonStyle(.borderedProminent)
    if let msg = model.claudeMessage {
      Text(msg).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
    }
    Text("Then ask Claude, for example:").font(.callout.weight(.semibold)).padding(.top, 4)
    Ask("What is in my health graph?")
    Ask("Which of my values are outside the guideline range?")
    Ask("Prepare my next doctor's visit.")
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
  let number: Int, title: String, symbol: String
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
          Text(LocalizedStringKey(s))
        }
      }
    }
  }
}

private struct CountRow: View {
  let value: Int, label: String
  var body: some View {
    GridRow {
      Text(value.formatted()).font(.title2.bold().monospacedDigit()).gridColumnAlignment(.trailing)
      Text(label).foregroundStyle(.secondary)
    }
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

private func copy(_ s: String) {
  NSPasteboard.general.clearContents()
  NSPasteboard.general.setString(s, forType: .string)
}
