// swift-tools-version:5.9
// This Package.swift enables building and testing the non-UI layers
// (Models, APIClient, Services) on macOS without the tvOS SDK.
// The actual tvOS app is built via the Xcode project (project.yml / KidsTube.xcodeproj).

import PackageDescription

let package = Package(
    name: "KidsTube",
    platforms: [.macOS(.v14), .tvOS(.v17)],
    targets: [
        .target(
            name: "KidsTubeCore",
            path: "Sources",
            exclude: [
                "Views",          // SwiftUI views require tvOS
                "App"             // App entry point requires tvOS
            ]
        ),
        .testTarget(
            name: "KidsTubeCoreTests",
            dependencies: ["KidsTubeCore"],
            path: "Tests"
        )
    ]
)
