// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "WardrobeApp",
    defaultLocalization: "en",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .executable(name: "WardrobeApp", targets: ["WardrobeApp"])
    ],
    targets: [
        .executableTarget(
            name: "WardrobeApp",
            path: "Sources/WardrobeApp"
        )
    ]
)
