import AppKit
import Foundation

/// The Klarbefund anamnesis skill (plugins/klarbefund/skills/klarbefund-anamnesis in the repository),
/// bundled with the app and saved as the zip Claude's Customize → Skills → Upload takes. A skill holds
/// the method only: the health data stays in the graph, read through the extension.
enum SkillExport {
  static let name = "klarbefund-anamnesis"
  static var folder: URL? { Bundle.main.url(forResource: name, withExtension: nil) }

  /// Zips the bundled skill folder (folder at the zip's root) and asks where to save it.
  @MainActor static func save() -> String {
    guard let folder else { return "The skill is missing from this build." }
    var zipped: URL?, failure: NSError?
    var coordinated: NSError?
    NSFileCoordinator().coordinate(readingItemAt: folder, options: .forUploading, error: &coordinated) { zip in
      // The zip lives only for this block: copy it out before it is removed.
      let copy = FileManager.default.temporaryDirectory.appendingPathComponent("\(name).zip")
      try? FileManager.default.removeItem(at: copy)
      do { try FileManager.default.copyItem(at: zip, to: copy); zipped = copy } catch { failure = error as NSError }
    }
    guard let zipped else { return "Could not zip the skill: \(coordinated ?? failure ?? NSError())" }
    let panel = NSSavePanel()
    panel.nameFieldStringValue = "\(name).zip"
    panel.allowedContentTypes = [.zip]
    panel.message = "Save the Klarbefund skill, then add it in Claude: Customize → Skills → + → Upload a skill."
    guard panel.runModal() == .OK, let target = panel.url else { return "" }
    do {
      try? FileManager.default.removeItem(at: target)
      try FileManager.default.copyItem(at: zipped, to: target)
      NSWorkspace.shared.activateFileViewerSelecting([target])
      return "Saved \(target.lastPathComponent). In Claude: Customize → Skills → + → Upload a skill, and choose it."
    } catch {
      return "Could not save the skill: \(error.localizedDescription)"
    }
  }
}
