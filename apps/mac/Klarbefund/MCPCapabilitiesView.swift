import SwiftUI

/// What the Klarbefund MCP server offers Claude: its tools, prompts and guides,
/// read from MCPCatalog, the list the helper (klarbefund-mcp) serves.
struct MCPCapabilitiesView: View {
  @Environment(\.dismiss) private var dismiss
  /// False only for the docs render: ImageRenderer draws no scroll view and no AppKit controls.
  var scrolls = true

  private var security: MCPCatalog.Guide? { MCPCatalog.guides.first { $0.name == "security" } }

  var body: some View {
    VStack(spacing: 0) {
      if scrolls {
        ScrollView { content }
      } else {
        content
      }
      Divider()
      HStack {
        Text("Not medical advice: help to understand your data and prepare questions for your doctor.")
          .font(.caption).foregroundStyle(.secondary)
        Spacer()
        if renderingForDocs {
          Text("Done").padding(.horizontal, 14).padding(.vertical, 4)
            .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 6)).foregroundStyle(.white)
        } else {
          Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
        }
      }
      .padding(.horizontal, 24).padding(.vertical, 12)
    }
    .frame(width: 720)
    .frame(height: scrolls ? 640 : nil)
  }

  private var content: some View {
    VStack(alignment: .leading, spacing: 18) {
      header
      CatalogSection(title: "Tools", detail: "2, read-only", symbol: "wrench.and.screwdriver") { tools }
      CatalogSection(title: "Prompts", detail: "\(MCPCatalog.prompts.count), in Claude's prompt menu (+)",
                     symbol: "text.bubble") { prompts }
      CatalogSection(title: "Guides", detail: "\(MCPCatalog.guides.count) resources Claude can read",
                     symbol: "book") { guideList }
      if let security {
        CatalogSection(title: "Security", detail: security.uri, symbol: "lock.shield") {
          MarkdownText(security.text, title: false)
        }
      }
    }
    .padding(24)
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private var header: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text("What Claude can do here").font(.largeTitle.bold())
      Text("\(MCPCatalog.serverTitle), the MCP server Klarbefund for Mac gives Claude Desktop.")
        .foregroundStyle(.secondary)
      Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 6) {
        Fact(label: "Server", value: "\(MCPCatalog.serverTitle) (\(MCPCatalog.serverName))")
        Fact(label: "Transport", value: "stdio, local, read-only")
        Fact(label: "Protocol", value: "MCP \(MCPCatalog.modernVersions.joined(separator: ", ")) (stateless), "
          + "\(MCPCatalog.legacyVersions.joined(separator: ", ")) (initialize)")
        Fact(label: "Authorization", value: "OAuth 2.1 applies to HTTP transports; a local stdio server "
          + "takes no credentials: macOS decides who can start it and what it can read.")
      }
      .font(.callout)
    }
  }

  private var tools: some View {
    VStack(alignment: .leading, spacing: 8) {
      Item(title: "get_schema", detail: "Labels and relationship types in your health graph, with counts.")
      Item(title: "read_cypher", detail: "One read-only Cypher query (MATCH ... RETURN), at most 500 rows. "
        + "Queries that would write are rejected.")
    }
  }

  private var prompts: some View {
    VStack(alignment: .leading, spacing: 14) {
      ForEach(MCPCatalog.Group.allCases, id: \.self) { group in
        let items = MCPCatalog.prompts.filter { $0.group == group }
        if !items.isEmpty {
          VStack(alignment: .leading, spacing: 8) {
            Text(group.rawValue).font(.headline)
            ForEach(items, id: \.name) { PromptRow(prompt: $0) }
          }
        }
      }
    }
  }

  private var guideList: some View {
    VStack(alignment: .leading, spacing: 10) {
      ForEach(MCPCatalog.guides, id: \.uri) { g in
        DisclosureGroup {
          MarkdownText(g.text)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.background, in: RoundedRectangle(cornerRadius: 8))
        } label: {
          VStack(alignment: .leading, spacing: 2) {
            Text(g.title).font(.callout.weight(.semibold))
            Text(g.description).font(.caption).foregroundStyle(.secondary)
            Text(g.uri).font(.caption.monospaced()).foregroundStyle(.tertiary).textSelection(.enabled)
          }
        }
      }
    }
  }
}

private struct CatalogSection<Content: View>: View {
  let title: String, detail: String, symbol: String
  @ViewBuilder var content: Content
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline, spacing: 8) {
        Label(title, systemImage: symbol).font(.title3.weight(.semibold))
        Text(detail).font(.callout).foregroundStyle(.secondary)
      }
      content
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16))
  }
}

private struct Fact: View {
  let label: String, value: String
  var body: some View {
    GridRow {
      Text(label).foregroundStyle(.secondary).gridColumnAlignment(.trailing)
      Text(value).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
  }
}

private struct Item: View {
  let title: String, detail: String
  var body: some View {
    VStack(alignment: .leading, spacing: 2) {
      Text(title).font(.callout.monospaced().weight(.semibold))
      Text(detail).font(.callout).foregroundStyle(.secondary)
    }
  }
}

private struct PromptRow: View {
  let prompt: MCPCatalog.Prompt
  var body: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 2) {
        Text("“\(prompt.title)”").font(.callout.weight(.medium))
        Text(prompt.description).font(.caption).foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
        if !prompt.arguments.isEmpty {
          Text(prompt.arguments.map { $0.required ? $0.name : "\($0.name) (optional)" }
            .joined(separator: ", "))
            .font(.caption.monospaced()).foregroundStyle(.tertiary)
        }
      }
      Spacer()
      if renderingForDocs {
        Image(systemName: "doc.on.doc").foregroundStyle(Color.accentColor)
      } else {
        Button { copy(prompt.ask) } label: { Image(systemName: "doc.on.doc") }
          .buttonStyle(.borderless).help("Copy")
      }
    }
  }
}

/// The guides' Markdown, block by block: headings, list items and paragraphs,
/// with inline emphasis and code. Selectable.
private struct MarkdownText: View {
  let blocks: [(kind: Kind, text: String)]
  enum Kind { case title, heading, bullet, number(String), paragraph }

  /// `title: false` leaves out the "# " heading, where the section already names it.
  init(_ markdown: String, title: Bool = true) {
    var out: [(Kind, String)] = []
    for raw in markdown.split(separator: "\n", omittingEmptySubsequences: true) {
      let line = raw.trimmingCharacters(in: .whitespaces)
      if line.hasPrefix("## ") {
        out.append((.heading, String(line.dropFirst(3))))
      } else if line.hasPrefix("# ") {
        if title { out.append((.title, String(line.dropFirst(2)))) }
      } else if line.hasPrefix("- ") {
        out.append((.bullet, String(line.dropFirst(2))))
      } else if let dot = line.firstIndex(of: "."), line[..<dot].allSatisfy(\.isNumber), !line[..<dot].isEmpty,
        line[line.index(after: dot)...].hasPrefix(" ")
      {
        out.append((.number(String(line[..<dot])), String(line[line.index(dot, offsetBy: 2)...])))
      } else {
        out.append((.paragraph, line))
      }
    }
    blocks = out
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
        switch block.kind {
        case .title: inline(block.text).font(.headline)
        case .heading: inline(block.text).font(.callout.weight(.semibold)).padding(.top, 4)
        case .bullet: marker("•", block.text)
        case .number(let n): marker("\(n).", block.text)
        case .paragraph: inline(block.text)
        }
      }
    }
    .font(.callout)
    .textSelection(.enabled)
  }

  private func marker(_ m: String, _ s: String) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: 6) {
      Text(m).foregroundStyle(.secondary)
      inline(s)
    }
  }

  private func inline(_ s: String) -> some View {
    let attributed = (try? AttributedString(
      markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(s)
    return Text(attributed).fixedSize(horizontal: false, vertical: true)
  }
}
