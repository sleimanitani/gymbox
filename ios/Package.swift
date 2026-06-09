// swift-tools-version:5.9
import PackageDescription

// GymboxSDK — the on-device half of gymbox (edge-first v0.7).
//
// The phone runs ALL real-time inference: MediaPipe Pose Lite produces a
// 33-joint skeleton, the DSLInterpreter (a straight port of the Python
// reference oracle) detects reps/phases live, sessions are buffered locally,
// and skeleton frames + annotations upload on Wi-Fi. The server is dumb
// storage + an /exercises OTA spec channel. See architecture.md §4, §6, §7.
//
// MediaPipe is integrated by the host app as a binary dependency (it is not a
// SwiftPM package); GymboxSDK consumes a `PoseSource` protocol so the heavy
// vision framework stays out of this package's dependency graph. See
// Pose/PoseSource.swift.
let package = Package(
    name: "GymboxSDK",
    platforms: [
        .iOS(.v16)
    ],
    products: [
        .library(name: "GymboxSDK", targets: ["GymboxSDK"])
    ],
    dependencies: [
        // GymboxProto carries the upload-envelope types (shared wire format).
        .package(path: "../gymbox-proto/swift")
    ],
    targets: [
        .target(
            name: "GymboxSDK",
            dependencies: [
                .product(name: "GymboxProto", package: "swift")
            ],
            path: "Sources/GymboxSDK"
        ),
        .testTarget(
            name: "GymboxSDKTests",
            dependencies: ["GymboxSDK"],
            path: "Tests/GymboxSDKTests",
            resources: [.copy("Fixtures")]
        )
    ]
)
