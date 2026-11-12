// swift-tools-version: 5.10
// The Mac side in Swift: `health-graph` CLI (import, query, list) and the
// QR-paired HTTPS receiver for Klarbefund. Replaces `python -m health_graph`.
// Kept apart from the root package so the iPhone app (which only needs the
// HealthGraph library) never fetches the server dependencies.
import Foundation
import PackageDescription

// The repository root holds the HealthGraph library. A path dependency is named
// after its folder, which is whatever the clone is called.
let repoRoot = URL(fileURLWithPath: Context.packageDirectory)
  .deletingLastPathComponent().deletingLastPathComponent()

let package = Package(
  name: "HealthGraphMac",
  platforms: [.macOS(.v13)],
  products: [.executable(name: "health-graph", targets: ["health-graph"])],
  dependencies: [
    .package(path: repoRoot.path),
    .package(url: "https://github.com/apple/swift-nio", from: "2.65.0"),
    .package(url: "https://github.com/apple/swift-nio-ssl", from: "2.27.0"),
    .package(url: "https://github.com/apple/swift-certificates", from: "1.5.0"),
    .package(url: "https://github.com/apple/swift-asn1", from: "1.1.0"),
    .package(url: "https://github.com/apple/swift-crypto", from: "3.0.0"),
    .package(url: "https://github.com/apple/swift-argument-parser", from: "1.3.0"),
  ],
  targets: [
    .target(
      name: "HealthGraphReceiver",
      dependencies: [
        .product(name: "HealthGraph", package: repoRoot.lastPathComponent),
        .product(name: "NIOCore", package: "swift-nio"),
        .product(name: "NIOPosix", package: "swift-nio"),
        .product(name: "NIOHTTP1", package: "swift-nio"),
        .product(name: "NIOSSL", package: "swift-nio-ssl"),
        .product(name: "X509", package: "swift-certificates"),
        .product(name: "SwiftASN1", package: "swift-asn1"),
        .product(name: "Crypto", package: "swift-crypto"),
      ]),
    .executableTarget(
      name: "health-graph",
      dependencies: [
        "HealthGraphReceiver",
        .product(name: "HealthGraph", package: repoRoot.lastPathComponent),
        .product(name: "ArgumentParser", package: "swift-argument-parser"),
      ]),
    .testTarget(name: "HealthGraphReceiverTests", dependencies: ["HealthGraphReceiver"]),
  ]
)
