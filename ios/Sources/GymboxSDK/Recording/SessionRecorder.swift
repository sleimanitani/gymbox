import Foundation

// SessionRecorder buffers a live training session on-device: it accumulates
// pose frames into a SkeletonStream, runs the DSLInterpreter to produce live
// rep/phase annotations, and packages everything for upload. Sessions persist
// locally until a Wi-Fi upload succeeds (architecture.md §6, §7).
//
// MVP-α status: frame buffering and annotation accumulation are CONCRETE; the
// live-interpretation hook depends on DSLInterpreter (Gate B) and is stubbed.

/// A locally-buffered annotation, bound to a stable client_annotation_id so
/// later corrections can target it by identity, never by position
/// (architecture.md §8).
public struct LocalAnnotation: Sendable {
    public let clientAnnotationId: String
    public let layerId: String
    public let startSeconds: Double
    public let endSeconds: Double
    public let value: String
    public let source: String       // "inference" | "user" | "replay"
    public let confidence: Double?

    public init(clientAnnotationId: String = UUID().uuidString,
                layerId: String, startSeconds: Double, endSeconds: Double,
                value: String, source: String = "inference", confidence: Double? = nil) {
        self.clientAnnotationId = clientAnnotationId
        self.layerId = layerId
        self.startSeconds = startSeconds
        self.endSeconds = endSeconds
        self.value = value
        self.source = source
        self.confidence = confidence
    }
}

/// A complete buffered session, ready to hand to the Uploader.
public struct RecordedSession: Sendable {
    public let clientSessionId: String
    public let exerciseId: String
    public let startedAtUTC: Date
    public let endedAtUTC: Date
    public let weightKg: Double?
    public let stream: SkeletonStream
    public let annotations: [LocalAnnotation]
}

public final class SessionRecorder {
    public let clientSessionId: String
    public let exerciseId: String
    public let weightKg: Double?
    private let spec: ExerciseSpec
    private let sampleRateHz: Double

    private var frames: [Frame] = []
    private var annotations: [LocalAnnotation] = []
    private var startedAt: Date?
    private var frameIndex = 0

    public init(exerciseId: String, spec: ExerciseSpec, weightKg: Double? = nil,
                sampleRateHz: Double = 15.0,
                clientSessionId: String = UUID().uuidString) {
        self.clientSessionId = clientSessionId
        self.exerciseId = exerciseId
        self.spec = spec
        self.weightKg = weightKg
        self.sampleRateHz = sampleRateHz
    }

    /// Ingest one live pose observation. CONCRETE — buffers the frame.
    public func ingest(_ obs: PoseObservation) {
        if startedAt == nil { startedAt = Date() }
        frames.append(Frame(frameIndex: frameIndex,
                             tSeconds: obs.tSeconds,
                             keypoints: obs.landmarks))
        frameIndex += 1
    }

    /// Append an annotation (e.g. a user correction made mid-session).
    public func add(_ annotation: LocalAnnotation) {
        annotations.append(annotation)
    }

    /// Current buffered stream.
    public var stream: SkeletonStream {
        SkeletonStream(sampleRateHz: sampleRateHz, frames: frames)
    }

    /// Re-run interpretation over the full buffered stream to (re)generate
    /// rep/phase annotations. Depends on DSLInterpreter (Gate B). STUB.
    public func reinterpret() {
        // TODO (ROADMAP Step 8): once DSLInterpreter.interpret is ported and
        // passes Gate B, run it here and translate InterpretResult into
        // LocalAnnotation rows on the `rep` and `rep_phase` layers, preserving
        // stable client_annotation_ids across re-interpretation so corrections
        // survive. Until then, recording still works; only auto-annotation is
        // pending.
        fatalError("SessionRecorder.reinterpret: pending DSLInterpreter port (ROADMAP Step 8)")
    }

    /// Finalize the session for upload. CONCRETE.
    public func finish() -> RecordedSession {
        RecordedSession(
            clientSessionId: clientSessionId,
            exerciseId: exerciseId,
            startedAtUTC: startedAt ?? Date(),
            endedAtUTC: Date(),
            weightKg: weightKg,
            stream: stream,
            annotations: annotations
        )
    }
}
