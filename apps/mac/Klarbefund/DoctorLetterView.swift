import AppKit
import HealthGraph
import SwiftUI
import UniformTypeIdentifiers
import WebKit

/// The doctor's letter, in its own window: for the GP or a specialist (one health risk), in German
/// or English, previewed as the A4 page it prints as, saved as a PDF or printed. Built on this Mac
/// from Claude's read-only snapshot (HealthGraph's `DoctorLetter`); nothing is loaded from anywhere.
struct DoctorLetterView: View {
  @ObservedObject var model: AppModel

  enum Kind: String, CaseIterable, Identifiable {
    case gp, specialist
    var id: String { rawValue }
  }

  @State private var kind: Kind = .gp
  @State private var risk = ""
  @State private var language = DoctorLetter.Language(locale: Locale.current)
  @State private var risks: [(id: String, name: String, values: Int)] = []
  @State private var html = ""
  @State private var ready = false
  @State private var message: String?
  @State private var web = WebHolder()

  private var variant: DoctorLetter.Variant {
    kind == .specialist && !risk.isEmpty ? .specialist(risk) : .gp
  }
  private var reloadKey: String { "\(variant)|\(language.rawValue)|\(model.snapshotVersion)" }

  var body: some View {
    VStack(spacing: 0) {
      controls.padding(.horizontal, 16).padding(.vertical, 10)
      Divider()
      LetterWebView(html: html, holder: web)
      if let message {
        Divider()
        Text(message).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16).padding(.vertical, 8)
      }
    }
    .task(id: reloadKey) { await load() }
  }

  private var controls: some View {
    HStack(spacing: 14) {
      Picker("For", selection: $kind) {
        Text("GP").tag(Kind.gp)
        Text("Specialist").tag(Kind.specialist)
      }
      .pickerStyle(.segmented).fixedSize()
      .help("GP: an overview of everything. Specialist: one health risk, its markers and the risks it connects to.")
      if kind == .specialist {
        Picker("Risk", selection: $risk) {
          ForEach(risks.filter { $0.values > 0 }, id: \.id) { r in
            Text("\(r.name) (\(r.values) values)").tag(r.id)
          }
        }
        .fixedSize()
        .disabled(risks.allSatisfy { $0.values == 0 })
      }
      Picker("Language", selection: $language) {
        Text("Deutsch").tag(DoctorLetter.Language.de)
        Text("English").tag(DoctorLetter.Language.en)
      }
      .pickerStyle(.segmented).fixedSize().labelsHidden()
      Spacer()
      Button { savePDF() } label: { Label("Save as PDF…", systemImage: "arrow.down.doc") }
        .disabled(!ready)
      Button { printLetter() } label: { Label("Print…", systemImage: "printer") }
        .disabled(!ready)
    }
  }

  /// Builds the letter off the main thread from the read-only snapshot.
  private func load() async {
    let variant = variant, language = language
    let result = await Task.detached(priority: .userInitiated) {
      Result { () throws -> (String, [(id: String, name: String, values: Int)]) in
        try Snapshot.read { store in
          let letter = try store.doctorLetter(variant)
          return (letter.html(language: language), try store.letterRisks())
        }
      }
    }.value
    switch result {
    case .success(let (page, found)):
      html = page
      risks = found
      ready = true
      if kind == .specialist && risk.isEmpty, let first = found.first(where: { $0.values > 0 }) { risk = first.id }
    case .failure(let error):
      html = Graph3DView.message("\(error)")
      ready = false
    }
  }

  private var fileName: String {
    let day = ISO8601DateFormatter.string(from: Date(), timeZone: .current, formatOptions: [.withFullDate])
    let base = language == .de ? "Arztbrief" : "Doctor's letter"
    let focus = variant.riskId.map { " \($0)" } ?? (language == .de ? " Hausarzt" : " GP")
    return "\(base)\(focus) \(day).pdf"
  }

  private func savePDF() {
    guard let webView = web.view else { return }
    let panel = NSSavePanel()
    panel.allowedContentTypes = [.pdf]
    panel.nameFieldStringValue = fileName
    panel.canCreateDirectories = true
    panel.begin { response in
      guard response == .OK, let url = panel.url else { return }
      LetterPDF.save(webView, to: url) { ok in
        message = ok ? "Saved \(url.lastPathComponent): A4, ready to print or to send." : "The PDF could not be saved."
      }
    }
  }

  private func printLetter() {
    guard let webView = web.view else { return }
    LetterPDF.print(webView)
  }
}

/// The web view that shows the letter, kept so Save and Print can reach it.
final class WebHolder {
  weak var view: WKWebView?
}

struct LetterWebView: NSViewRepresentable {
  let html: String
  let holder: WebHolder

  final class Coordinator { var shown: String? }
  func makeCoordinator() -> Coordinator { Coordinator() }

  func makeNSView(context: Context) -> WKWebView {
    let config = WKWebViewConfiguration()
    config.websiteDataStore = .nonPersistent()  // nothing of the letter is kept on disk
    let web = WKWebView(frame: .zero, configuration: config)
    holder.view = web
    return web
  }

  func updateNSView(_ web: WKWebView, context: Context) {
    holder.view = web
    guard context.coordinator.shown != html else { return }
    context.coordinator.shown = html
    web.loadHTMLString(html, baseURL: nil)
  }
}

/// Printing the letter: A4 pages, the margins of a letter, a PDF saved without a panel or the
/// system print panel. WebKit paginates the page itself (headings stay with their tables, rows
/// are not split).
enum LetterPDF {
  static let a4 = NSSize(width: 595.28, height: 841.89)

  static func printInfo(saveTo url: URL?) -> NSPrintInfo {
    let info = NSPrintInfo(dictionary: [:])
    info.paperSize = a4
    info.orientation = .portrait
    info.topMargin = 36
    info.bottomMargin = 36
    info.leftMargin = 36
    info.rightMargin = 36
    info.horizontalPagination = .fit
    info.verticalPagination = .automatic
    info.isHorizontallyCentered = false
    info.isVerticallyCentered = false
    if let url {
      info.jobDisposition = .save
      info.dictionary()[NSPrintInfo.AttributeKey.jobSavingURL] = url
    }
    return info
  }

  /// Saves the letter shown in `web` as a multi-page A4 PDF at `url`. Runs modally for the web view's
  /// window, so WebKit can lay the pages out while the main run loop turns (a blocking `run()` makes
  /// WKWebView paginate without end).
  @MainActor static func save(_ web: WKWebView, to url: URL, done: @escaping (Bool) -> Void) {
    guard let window = web.window else { return done(false) }
    try? FileManager.default.removeItem(at: url)
    let op = web.printOperation(with: printInfo(saveTo: url))
    op.showsPrintPanel = false
    op.showsProgressPanel = false
    op.view?.frame = web.bounds  // WKWebView prints blank pages without a frame
    let finished = Finished { ok in done(ok && FileManager.default.fileExists(atPath: url.path)) }
    op.runModal(for: window, delegate: finished, didRun: #selector(Finished.printOperationDidRun(_:success:contextInfo:)),
                contextInfo: nil)
  }

  /// The print operation's callback; kept alive until it is called.
  final class Finished: NSObject {
    private static var running: Set<Finished> = []
    private let done: (Bool) -> Void

    init(_ done: @escaping (Bool) -> Void) {
      self.done = done
      super.init()
      Self.running.insert(self)
    }

    @objc func printOperationDidRun(_ op: NSPrintOperation, success: Bool, contextInfo: UnsafeMutableRawPointer?) {
      done(success)
      Self.running.remove(self)
    }
  }

  /// The system print panel, for a printer (or its own PDF menu).
  @MainActor static func print(_ web: WKWebView) {
    let op = web.printOperation(with: printInfo(saveTo: nil))
    op.showsPrintPanel = true
    op.showsProgressPanel = true
    op.view?.frame = web.bounds
    if let window = web.window {
      op.runModal(for: window, delegate: nil, didRun: nil, contextInfo: nil)
    } else {
      op.run()
    }
  }
}
