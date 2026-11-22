#if DEBUG
  import AppKit
  import HealthGraph
  import PDFKit
  import WebKit

  /// Debug-only renders for the docs and for checking the letter, from a store given on the command
  /// line (the synthetic sample graph): never Claude's snapshot, never the app's own graph.
  @MainActor enum DocsRender {
    final class Loaded: NSObject, WKNavigationDelegate {
      var done = false
      func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { done = true }
      func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { done = true }
    }

    /// The GP and cardiovascular letters in German and English: .html, .md, .pdf (A4, through the same
    /// print path as Save as PDF…), and page 1 of each PDF as a PNG. Prints each PDF's page count.
    static func letters(store path: String, out: String, today: String?) {
      let outDir = URL(fileURLWithPath: out, isDirectory: true)
      try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
      let window = NSWindow(
        contentRect: NSRect(x: -4000, y: -4000, width: 794, height: 1123), styleMask: [.borderless],
        backing: .buffered, defer: false)
      let config = WKWebViewConfiguration()
      config.websiteDataStore = .nonPersistent()
      let web = WKWebView(frame: NSRect(x: 0, y: 0, width: 794, height: 1123), configuration: config)
      let loaded = Loaded()
      web.navigationDelegate = loaded
      window.contentView = web
      window.orderBack(nil)
      do {
        let letters = try Snapshot.read(URL(fileURLWithPath: path)) { store in
          [("gp", try store.doctorLetter(.gp, today: today)),
           ("cardiovascular", try store.doctorLetter(.specialist("cardiovascular"), today: today))]
        }
        for (name, letter) in letters {
          for lang in DoctorLetter.Language.allCases {
            let base = outDir.appendingPathComponent("letter-\(name)-\(lang.rawValue)")
            let html = letter.html(language: lang)
            try html.write(to: base.appendingPathExtension("html"), atomically: true, encoding: .utf8)
            try letter.markdown(language: lang).write(to: base.appendingPathExtension("md"), atomically: true, encoding: .utf8)
            loaded.done = false
            web.loadHTMLString(html, baseURL: nil)
            let deadline = Date().addingTimeInterval(20)
            while !loaded.done && Date() < deadline { RunLoop.main.run(until: Date().addingTimeInterval(0.05)) }
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))  // layout settles
            let pdf = base.appendingPathExtension("pdf")
            var saved: Bool?
            LetterPDF.save(web, to: pdf) { saved = $0 }
            let printing = Date().addingTimeInterval(30)
            while saved == nil && Date() < printing {
              RunLoop.main.run(until: Date().addingTimeInterval(0.05))
              let size = (try? FileManager.default.attributesOfItem(atPath: pdf.path)[.size] as? Int) ?? 0
              if size > 20_000_000 { print("error: \(pdf.path) grows without end"); exit(1) }
            }
            let pages = PDFDocument(url: pdf)?.pageCount ?? 0
            print("\(pdf.path): saved \(saved.map(String.init) ?? "timed out"), \(pages) pages")
            fflush(stdout)
            if let page = PDFDocument(url: pdf)?.page(at: 0) {
              let box = page.bounds(for: .mediaBox)
              let image = page.thumbnail(of: NSSize(width: box.width * 2, height: box.height * 2), for: .mediaBox)
              if let tiff = image.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff) {
                try rep.representation(using: .png, properties: [:])?.write(to: base.appendingPathExtension("png"))
              }
            }
          }
        }
      } catch {
        print("error: \(error)")
      }
    }
  }
#endif
