import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// A QR code (error correction M) as a module matrix, for the terminal and PNG.
public struct QRCode {
  /// `true` = dark module. Includes the generator's quiet zone.
  public let modules: [[Bool]]

  public init?(_ text: String) {
    guard let filter = CIFilter(name: "CIQRCodeGenerator") else { return nil }
    filter.setValue(Data(text.utf8), forKey: "inputMessage")
    filter.setValue("M", forKey: "inputCorrectionLevel")
    guard let image = filter.outputImage,
      let cg = CIContext().createCGImage(image, from: image.extent)
    else { return nil }
    let w = cg.width
    let h = cg.height
    var pixels = [UInt8](repeating: 255, count: w * h)
    guard
      let ctx = CGContext(
        data: &pixels, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
        space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)
    else { return nil }
    ctx.interpolationQuality = .none
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
    modules = (0..<h).map { y in (0..<w).map { x in pixels[y * w + x] < 128 } }
  }

  /// Two modules per character (upper half block), black on white whatever
  /// the terminal's theme, so the phone's camera reads it.
  public func terminal(border: Int = 2) -> String {
    let size = modules.count + 2 * border
    func dark(_ x: Int, _ y: Int) -> Bool {
      let (mx, my) = (x - border, y - border)
      return modules.indices.contains(my) && modules[my].indices.contains(mx) && modules[my][mx]
    }
    var out = ""
    for y in stride(from: 0, to: size, by: 2) {
      for x in 0..<size {
        let top = dark(x, y) ? 30 : 97
        let bottom = y + 1 < size && dark(x, y + 1) ? 40 : 107
        out += "\u{1B}[\(top);\(bottom)m\u{2580}"
      }
      out += "\u{1B}[0m\n"
    }
    return out
  }

  /// A crisp PNG (`scale` pixels per module).
  public func png(scale: Int = 8, border: Int = 3) -> Data? {
    let size = (modules.count + 2 * border) * scale
    guard
      let ctx = CGContext(
        data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)
    else { return nil }
    ctx.setFillColor(gray: 1, alpha: 1)
    ctx.fill(CGRect(x: 0, y: 0, width: size, height: size))
    ctx.setFillColor(gray: 0, alpha: 1)
    for (y, row) in modules.enumerated() {
      for (x, isDark) in row.enumerated() where isDark {
        // CGContext's origin is bottom-left: flip rows.
        let top = size - (y + border + 1) * scale
        ctx.fill(CGRect(x: (x + border) * scale, y: top, width: scale, height: scale))
      }
    }
    guard let image = ctx.makeImage() else { return nil }
    let data = NSMutableData()
    guard
      let dest = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil)
    else { return nil }
    CGImageDestinationAddImage(dest, image, nil)
    return CGImageDestinationFinalize(dest) ? data as Data : nil
  }
}
