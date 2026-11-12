// swift-tools-version: 6.0
// HealthGraph: Klarbefund FHIR bundles and Apple Health weekly means in a
// local Relate graph. One library for the iPhone (Klarbefund's on-device
// graph) and the Mac (swift/mac: CLI + receiver). Same graph as the Python
// reference in health_graph/, checked by the tests.
import PackageDescription

let package = Package(
  name: "HealthGraph",
  platforms: [.iOS(.v16), .macOS(.v13)],
  products: [.library(name: "HealthGraph", targets: ["HealthGraph"])],
  dependencies: [.package(url: "https://github.com/relatedb/relate", from: "1.0.0")],
  targets: [
    .target(
      name: "HealthGraph",
      dependencies: [.product(name: "Relate", package: "relate")],
      path: "swift/Sources/HealthGraph"),
    .testTarget(
      name: "HealthGraphTests",
      dependencies: ["HealthGraph"],
      path: "swift/Tests/HealthGraphTests"),
  ]
)
