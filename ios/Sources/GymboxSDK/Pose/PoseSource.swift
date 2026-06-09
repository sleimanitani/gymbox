import Foundation

// PoseSource abstracts the pose estimator. MediaPipe Pose Lite is integrated by
// the HOST APP as a binary dependency (it ships as an .xcframework / CocoaPod,
// not a SwiftPM package), so GymboxSDK depends only on this protocol and never
// links the vision framework itself. See architecture.md §4, §6.
//
// The host app wraps its MediaPipe pose landmarker in a type conforming to
// PoseSource and hands frames to GymboxSDK. A no-op/replay implementation is
// provided for tests and for batch replay of recorded skeletons.

/// One emitted pose: 33 landmarks (x, y, visibility), normalized to [0, 1],
/// plus a capture timestamp. Index order MUST match Keypoints.names.
public struct PoseObservation: Sendable {
    public let tSeconds: Double
    public let landmarks: [SIMD3<Double>]

    public init(tSeconds: Double, landmarks: [SIMD3<Double>]) {
        precondition(landmarks.count == Keypoints.count,
                     "expected \(Keypoints.count) landmarks, got \(landmarks.count)")
        self.tSeconds = tSeconds
        self.landmarks = landmarks
    }
}

/// A source of pose observations. The host app's MediaPipe wrapper conforms to
/// this; GymboxSDK consumes it without knowing about the camera or the model.
public protocol PoseSource: AnyObject {
    /// Sample rate the source intends to deliver at (e.g. 15 Hz in MVP-α).
    var sampleRateHz: Double { get }

    /// Begin emitting observations to the handler on a background queue.
    func start(_ onObservation: @escaping (PoseObservation) -> Void)

    /// Stop emitting.
    func stop()
}

/// A PoseSource that replays a recorded SkeletonStream — used by tests and by
/// batch replay (no camera, no MediaPipe). CONCRETE.
public final class ReplayPoseSource: PoseSource {
    public let sampleRateHz: Double
    private let frames: [Frame]
    private var cancelled = false

    public init(stream: SkeletonStream) {
        self.sampleRateHz = stream.sampleRateHz
        self.frames = stream.frames
    }

    public func start(_ onObservation: @escaping (PoseObservation) -> Void) {
        cancelled = false
        for frame in frames where !cancelled {
            onObservation(PoseObservation(tSeconds: frame.tSeconds, landmarks: frame.keypoints))
        }
    }

    public func stop() { cancelled = true }
}
