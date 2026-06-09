// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "GymboxProto",
    platforms: [.iOS(.v16)],
    products: [
        .library(name: "GymboxProto", targets: ["GymboxProto"]),
    ],
    dependencies: [
        // Generated Swift protobuf bindings depend on SwiftProtobuf at runtime.
        .package(url: "https://github.com/apple/swift-protobuf.git", from: "1.25.0"),
    ],
    targets: [
        .target(
            name: "GymboxProto",
            dependencies: [
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
            ]
        ),
    ]
)
