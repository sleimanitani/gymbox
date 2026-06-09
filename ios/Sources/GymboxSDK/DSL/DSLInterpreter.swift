import Foundation

// DSLInterpreter — the on-device port of the Python reference oracle
// (gymbox/pipeline/rep.py). This is the GATE B target: run against the same
// bicep_curl_1 fixture, its output must match the Python interpreter to
// >=98% frame-phase identity, identical rep count, +/-2-frame boundaries.
//
// Build order (architecture.md §12): Gate A (Python) is implemented and passing
// FIRST. Only then is this ported, with the Python output as ground truth. The
// signal front-end (Signal.swift) and `evaluatePhase` are already provided and
// locked; the detection core below is the work.

/// Per-frame context handed to phase evaluation. Mirrors the Python FrameContext.
public struct FrameContext {
    public let velocity: Double
    public let direction: Direction?
    public let positionBand: PositionBand?
    public let signChangedWithinMs: Double?  // ms since last velocity sign change, or nil

    public init(velocity: Double, direction: Direction?,
                positionBand: PositionBand?, signChangedWithinMs: Double?) {
        self.velocity = velocity
        self.direction = direction
        self.positionBand = positionBand
        self.signChangedWithinMs = signChangedWithinMs
    }
}

/// Dynamic position bands locked from the first completed rep's extremes
/// (architecture.md §10). low/high are the outer `bandFrac` of the range; mid
/// is everything between.
public struct DynamicBands {
    public let bandFrac: Double
    private var lo: Double?
    private var hi: Double?

    public init(bandFrac: Double = 0.25) { self.bandFrac = bandFrac }

    public var isFitted: Bool { lo != nil && hi != nil }

    /// Lock the bands from the first rep's min/max signal value.
    public mutating func fit(min minValue: Double, max maxValue: Double) {
        lo = minValue
        hi = maxValue
    }

    /// Classify a signal value into a band. Returns nil until fitted.
    public func band(of value: Double) -> PositionBand? {
        guard let lo, let hi, hi > lo else { return nil }
        let span = hi - lo
        let lowCut = lo + bandFrac * span
        let highCut = hi - bandFrac * span
        if value <= lowCut { return .low }
        if value >= highCut { return .high }
        return .mid
    }
}

public enum DSLInterpreter {

    /// Evaluate phase rules for one frame, first-match-wins in
    /// PhaseLabel.evaluationOrder (RESET first). PROVIDED & LOCKED — mirrors the
    /// Python `evaluate_phase`. Do not change this logic during the port.
    public static func evaluatePhase(_ spec: PhaseSpec, _ ctx: FrameContext) -> PhaseLabel {
        for rule in spec.orderedRules() {
            if conditionHolds(rule.when, ctx) {
                return rule.label
            }
        }
        return spec.defaultLabel
    }

    /// All present predicate fields must hold (logical AND). PROVIDED & LOCKED.
    static func conditionHolds(_ cond: PhaseConditions, _ ctx: FrameContext) -> Bool {
        if let lt = cond.absVLt, !(abs(ctx.velocity) < lt) { return false }
        if let gt = cond.absVGt, !(abs(ctx.velocity) > gt) { return false }
        if let dir = cond.direction, ctx.direction != dir { return false }
        if let band = cond.positionBand, ctx.positionBand != band { return false }
        if let within = cond.signChangedWithinMs {
            guard let since = ctx.signChangedWithinMs, since <= within else { return false }
        }
        return true
    }

    /// Map a velocity to a movement direction along the (inverted) signal.
    /// PROVIDED.
    public static func directionLabel(_ v: Double, deadZone: Double = 1e-6) -> Direction? {
        if v > deadZone { return .towardHigh }
        if v < -deadZone { return .towardLow }
        return nil
    }

    // MARK: - the work (Gate B)

    /// Run the interpreter over a stream.
    ///
    /// Front-end is wired; the detection core is the port target. Steps mirror
    /// the Python contract exactly:
    ///   1. Detect extrema on `smoothed`; pair into reps per `spec.rep`.
    ///   2. bands.fit(min:max:) from the first completed rep.
    ///   3. Per frame, build FrameContext (velocity, direction, band,
    ///      sign-change recency) and label via evaluatePhase.
    ///   4. Coalesce frame phases into PhaseSegments; assemble the result.
    ///
    /// Until ported, traps so Gate B clearly reports "not done yet".
    public static func interpret(spec: ExerciseSpec, stream: SkeletonStream) -> InterpretResult {
        // --- front-end (provided) -----------------------------------------
        let raw = Signal.extractJointAxis(stream, spec.signal)
        let smoothed = Signal.smooth(raw, spec.smoothing)
        let _ = Signal.velocity(smoothed, sampleRateHz: stream.sampleRateHz)
        var _bands = DynamicBands(bandFrac: 0.25)
        _ = _bands

        // --- detection core (IMPLEMENT — Gate B) --------------------------
        fatalError(
            "DSLInterpreter.interpret: port extrema_pair rep detection + per-frame " +
            "phase labeling from gymbox/pipeline/rep.py (ROADMAP Step 7). The signal " +
            "front-end and evaluatePhase are provided. Target: Gate B vs the Python " +
            "oracle on bicep_curl_1 (>=98% frame-phase identity, identical rep count)."
        )
    }
}
