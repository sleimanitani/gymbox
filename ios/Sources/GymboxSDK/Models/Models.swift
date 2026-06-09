import Foundation

// Core value types shared across the SDK. These mirror the Python
// pipeline.types module so the two implementations stay legible side by side
// (Gate B compares them frame-for-frame). See architecture.md §10, §12.

/// Movement phase labels. Order of *declaration* is irrelevant; evaluation
/// order is fixed by `PhaseLabel.evaluationOrder` (RESET first, first-match-wins).
public enum PhaseLabel: String, Codable, CaseIterable, Sendable {
    case con = "CON"                   // concentric — shortening under load
    case ecc = "ECC"                   // eccentric — lengthening under load
    case isoLoaded = "ISO_LOADED"      // hold, muscle lengthened & resisting (db_curl: bottom)
    case isoUnloaded = "ISO_UNLOADED"  // hold, muscle shortened, minimal tension (db_curl: top)
    case reset = "RESET"               // between-rep transition / not in a rep

    /// First-match-wins evaluation order. RESET is evaluated FIRST
    /// (architecture.md §10). Must match Python PHASE_EVAL_ORDER exactly.
    public static let evaluationOrder: [PhaseLabel] = [
        .reset, .isoLoaded, .isoUnloaded, .con, .ecc
    ]
}

/// One pose frame: 33 (x, y, visibility) triples + a timestamp.
public struct Frame: Sendable {
    public let frameIndex: Int
    public let tSeconds: Double
    /// 33 landmarks in MediaPipe Pose order. Each is (x, y, visibility),
    /// image-normalized to [0, 1]. See Keypoints.swift.
    public let keypoints: [SIMD3<Double>]

    public init(frameIndex: Int, tSeconds: Double, keypoints: [SIMD3<Double>]) {
        self.frameIndex = frameIndex
        self.tSeconds = tSeconds
        self.keypoints = keypoints
    }

    /// (x, y) of a joint by index, dropping visibility.
    public func xy(_ jointIndex: Int) -> SIMD2<Double> {
        let kp = keypoints[jointIndex]
        return SIMD2(kp.x, kp.y)
    }
}

/// A buffered sequence of pose frames at a fixed sample rate.
public struct SkeletonStream: Sendable {
    public let sampleRateHz: Double
    public let frames: [Frame]

    public init(sampleRateHz: Double, frames: [Frame]) {
        self.sampleRateHz = sampleRateHz
        self.frames = frames
    }

    public var count: Int { frames.count }

    public var durationSeconds: Double {
        guard let first = frames.first, let last = frames.last else { return 0 }
        return last.tSeconds - first.tSeconds
    }
}

/// A detected repetition.
public struct RepEvent: Sendable, Equatable {
    public let index: Int          // 0-based rep number within the stream
    public let startSeconds: Double
    public let endSeconds: Double
    public let amplitude: Double   // normalized peak-to-peak of the tracked signal

    public init(index: Int, startSeconds: Double, endSeconds: Double, amplitude: Double) {
        self.index = index
        self.startSeconds = startSeconds
        self.endSeconds = endSeconds
        self.amplitude = amplitude
    }
}

/// A contiguous run of frames sharing one phase label.
public struct PhaseSegment: Sendable, Equatable {
    public let label: PhaseLabel
    public let startSeconds: Double
    public let endSeconds: Double
    public let startFrame: Int
    public let endFrame: Int

    public init(label: PhaseLabel, startSeconds: Double, endSeconds: Double,
                startFrame: Int, endFrame: Int) {
        self.label = label
        self.startSeconds = startSeconds
        self.endSeconds = endSeconds
        self.startFrame = startFrame
        self.endFrame = endFrame
    }
}

/// Output of the interpreter over a stream.
public struct InterpretResult: Sendable {
    public let reps: [RepEvent]
    public let phaseSegments: [PhaseSegment]
    public let framePhases: [PhaseLabel]

    public init(reps: [RepEvent], phaseSegments: [PhaseSegment], framePhases: [PhaseLabel]) {
        self.reps = reps
        self.phaseSegments = phaseSegments
        self.framePhases = framePhases
    }

    public var repCount: Int { reps.count }
}
