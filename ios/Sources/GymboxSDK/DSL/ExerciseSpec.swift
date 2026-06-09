import Foundation

// Codable mirror of the D6 DSL grammar (architecture.md §10). These decode the
// exact JSON the server's /exercises OTA channel serves and the Python
// ExerciseSpec emits. Field names use snake_case CodingKeys to match the wire
// form. Keep this aligned with gymbox/dsl/models.py.

public enum Axis: String, Codable, Sendable { case x, y, z }

public enum SignalType: String, Codable, Sendable {
    case jointAxis = "joint_axis"
    // Reserved for post-MVP-α: joint_angle, segment_angle, distance, composite.
}

public struct JointAxisSignal: Codable, Sendable {
    public let type: SignalType
    public let joint: String
    public let axis: Axis
    public let invert: Bool

    enum CodingKeys: String, CodingKey { case type, joint, axis, invert }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.type = try c.decode(SignalType.self, forKey: .type)
        self.joint = try c.decode(String.self, forKey: .joint)
        self.axis = try c.decodeIfPresent(Axis.self, forKey: .axis) ?? .y
        self.invert = try c.decodeIfPresent(Bool.self, forKey: .invert) ?? false
    }
}

public enum SmoothingMethod: String, Codable, Sendable {
    case savitzkyGolay = "savitzky_golay"
    case gaussian
    case none
}

public struct SmoothingSpec: Codable, Sendable {
    public let method: SmoothingMethod
    public let windowFrames: Int
    public let polyorder: Int?
    public let sigma: Double?

    enum CodingKeys: String, CodingKey {
        case method
        case windowFrames = "window_frames"
        case polyorder
        case sigma
    }

    /// Half-window emission delay in frames (architecture.md §10). The smoothed
    /// value at frame i depends on frames up to i + halfWindow, so live phase
    /// emission lags by this many frames.
    public var emissionDelayFrames: Int {
        switch method {
        case .savitzkyGolay, .gaussian: return windowFrames / 2
        case .none: return 0
        }
    }
}

public enum RepMethod: String, Codable, Sendable {
    case extremaPair = "extrema_pair"
    case velocityZeroCrossing = "velocity_zero_crossing"  // reserved
}

public enum CycleFrom: String, Codable, Sendable { case low, high }

public struct ExtremaPairRep: Codable, Sendable {
    public let method: RepMethod
    public let minAmplitude: Double
    public let minSeparationS: Double
    public let prominenceFrac: Double
    public let cycleFrom: CycleFrom

    enum CodingKeys: String, CodingKey {
        case method
        case minAmplitude = "min_amplitude"
        case minSeparationS = "min_separation_s"
        case prominenceFrac = "prominence_frac"
        case cycleFrom = "cycle_from"
    }
}

public enum PositionBand: String, Codable, Sendable { case low, mid, high }
public enum Direction: String, Codable, Sendable {
    case towardHigh = "toward_high"
    case towardLow = "toward_low"
}

/// A phase rule's predicate. All present fields must hold (logical AND).
public struct PhaseConditions: Codable, Sendable {
    public let absVLt: Double?
    public let absVGt: Double?
    public let direction: Direction?
    public let signChangedWithinMs: Double?
    public let positionBand: PositionBand?

    enum CodingKeys: String, CodingKey {
        case absVLt = "abs_v_lt"
        case absVGt = "abs_v_gt"
        case direction
        case signChangedWithinMs = "sign_changed_within_ms"
        case positionBand = "position_band"
    }
}

public struct PhaseRule: Codable, Sendable {
    public let label: PhaseLabel
    public let when: PhaseConditions
}

public struct PhaseSpec: Codable, Sendable {
    public let rules: [PhaseRule]
    public let defaultLabel: PhaseLabel

    enum CodingKeys: String, CodingKey {
        case rules
        case defaultLabel = "default"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.rules = try c.decode([PhaseRule].self, forKey: .rules)
        self.defaultLabel = try c.decodeIfPresent(PhaseLabel.self, forKey: .defaultLabel) ?? .reset
    }

    /// Rules sorted into PhaseLabel.evaluationOrder (RESET first), regardless of
    /// authoring order. First match wins. Mirrors Python `ordered_rules()`.
    public func orderedRules() -> [PhaseRule] {
        let rank = Dictionary(uniqueKeysWithValues:
            PhaseLabel.evaluationOrder.enumerated().map { ($1, $0) })
        return rules.sorted { (rank[$0.label] ?? .max) < (rank[$1.label] ?? .max) }
    }
}

/// Reserved for post-MVP-α learned models. Null in MVP-α.
public struct ModelSpec: Codable, Sendable {
    public let kind: String?
    public let uri: String?
    public let version: Int?
}

public struct ExerciseSpec: Codable, Sendable {
    public let id: String
    public let displayName: String
    public let schemaVersion: Int
    public let signal: JointAxisSignal
    public let smoothing: SmoothingSpec
    public let rep: ExtremaPairRep
    public let phase: PhaseSpec
    public let modelSpec: ModelSpec?

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case schemaVersion = "schema_version"
        case signal, smoothing, rep, phase
        case modelSpec = "model_spec"
    }

    public static func decode(from data: Data) throws -> ExerciseSpec {
        try JSONDecoder().decode(ExerciseSpec.self, from: data)
    }
}
