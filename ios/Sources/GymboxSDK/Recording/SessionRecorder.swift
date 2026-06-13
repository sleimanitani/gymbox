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

    /// Re-run interpretation over the full buffered stream to (re)generate the
    /// inference `rep` / `rep_phase` annotations. Safe to call repeatedly (e.g.
    /// as more frames arrive) — it is idempotent.
    ///
    /// Identity, not position (architecture.md §8): inference rows get
    /// deterministic `client_annotation_id`s derived from the session id + layer
    /// + ordinal, so a correction that targets one keeps resolving after a
    /// re-interpretation, and re-running never duplicates rows. Annotations the
    /// caller added (any `source` other than "inference" — e.g. user
    /// corrections) are preserved untouched.
    public func reinterpret() {
        let result = DSLInterpreter.interpret(spec: spec, stream: stream)

        // Keep everything the interpreter doesn't own; replace only inference rows.
        var rebuilt = annotations.filter { $0.source != "inference" }

        for rep in result.reps {
            rebuilt.append(LocalAnnotation(
                clientAnnotationId: "\(clientSessionId):rep:\(rep.index)",
                layerId: "rep",
                startSeconds: rep.startSeconds,
                endSeconds: rep.endSeconds,
                value: String(rep.index + 1),   // 1-based rep number (informational)
                source: "inference",
                confidence: nil
            ))
        }

        for (i, segment) in result.phaseSegments.enumerated() {
            rebuilt.append(LocalAnnotation(
                clientAnnotationId: "\(clientSessionId):rep_phase:\(i)",
                layerId: "rep_phase",
                startSeconds: segment.startSeconds,
                endSeconds: segment.endSeconds,
                value: segment.label.rawValue,   // materializer keys phase durations by this
                source: "inference",
                confidence: nil
            ))
        }

        annotations = rebuilt
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
