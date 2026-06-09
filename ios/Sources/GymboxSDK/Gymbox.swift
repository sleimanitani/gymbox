import Foundation

// Public entry point and version marker for GymboxSDK.

public enum GymboxSDKInfo {
    /// Keep in step with the Python package version and the proto schema.
    public static let version = "0.1.0"
}

/// Thin facade wiring the pieces a host app uses for one exercise session:
/// fetch the spec (OTA), record a session from a PoseSource, upload on Wi-Fi.
///
/// This is deliberately small — the host app owns the camera, the MediaPipe
/// PoseSource, network reachability, and persistence. GymboxSDK provides the
/// spec cache, the recorder, the (forthcoming) on-device interpreter, and the
/// upload envelope. See architecture.md §6.
public final class Gymbox {
    public let catalog: ExerciseCatalog
    public let uploader: Uploader

    public init(baseURL: URL, token: String,
                session: URLSession = .shared,
                catalogStore: CatalogStore? = nil) {
        self.catalog = ExerciseCatalog(baseURL: baseURL, token: token,
                                       session: session, store: catalogStore)
        self.uploader = Uploader(baseURL: baseURL, token: token, session: session)
    }

    /// Fetch (or revalidate) an exercise spec from the OTA channel.
    public func exerciseSpec(id: String) async throws -> ExerciseSpec {
        try await catalog.fetch(id: id)
    }

    /// Start a recorder for a given spec. Feed it PoseObservations, then call
    /// `finish()` and hand the result to `uploader.upload(...)`.
    public func makeRecorder(spec: ExerciseSpec, weightKg: Double? = nil,
                             sampleRateHz: Double = 15.0) -> SessionRecorder {
        SessionRecorder(exerciseId: spec.id, spec: spec,
                        weightKg: weightKg, sampleRateHz: sampleRateHz)
    }
}
