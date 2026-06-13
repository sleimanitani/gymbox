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

    /// Run the interpreter over a stream. Direct port of the Python reference
    /// oracle `gymbox/pipeline/rep.py interpret()` — the logic below must stay
    /// line-for-line faithful to it (Gate B compares the two frame-for-frame).
    ///   1. Detect alternating extrema on `smoothed`; pair into reps per `spec.rep`.
    ///   2. bands.fit(min:max:) from the first completed rep.
    ///   3. Per frame, build FrameContext (velocity, direction, band,
    ///      sign-change recency) and label via evaluatePhase.
    ///   4. Coalesce frame phases into PhaseSegments; assemble the result.
    public static func interpret(spec: ExerciseSpec, stream: SkeletonStream) -> InterpretResult {
        // --- front-end (provided) -----------------------------------------
        let raw = Signal.extractJointAxis(stream, spec.signal)
        let smoothed = Signal.smooth(raw, spec.smoothing)
        let vel = Signal.velocity(smoothed, sampleRateHz: stream.sampleRateHz)
        var bands = DynamicBands(bandFrac: 0.25)

        // --- detection core (ported from rep.py) --------------------------
        // 1. Alternating extrema (pivots) over the smoothed signal.
        let pivots = alternatingExtrema(smoothed, rep: spec.rep,
                                        sampleRateHz: stream.sampleRateHz)

        // 2. Pair pivots into reps; lock the dynamic bands from the FIRST rep.
        let reps = detectReps(pivots, smoothed: smoothed, stream: stream, rep: spec.rep)
        if let first = reps.first {
            let lo = Swift.min(smoothed[first.startFrame], smoothed[first.endFrame])
            let hi = smoothed[first.peakFrame]
            bands.fit(min: lo, max: hi)
        }

        // 3. Per-frame phase labeling. The offline oracle has full lookahead, so
        //    the bands locked from the first rep are applied to ALL frames (the
        //    emission delay only matters for streaming — same note as rep.py).
        let signChangeMs = msSinceSignChange(vel, sampleRateHz: stream.sampleRateHz)
        var framePhases: [PhaseLabel] = []
        framePhases.reserveCapacity(stream.count)
        for i in 0..<stream.count {
            let ctx = FrameContext(
                velocity: vel[i],
                direction: directionLabel(vel[i]),
                positionBand: bands.band(of: smoothed[i]),
                signChangedWithinMs: signChangeMs[i]
            )
            framePhases.append(evaluatePhase(spec.phase, ctx))
        }

        // 4. Coalesce into segments and assemble the result.
        let segments = coalesceSegments(framePhases, stream: stream)
        let repEvents = reps.map {
            RepEvent(index: $0.index, startSeconds: $0.startSeconds,
                     endSeconds: $0.endSeconds, amplitude: $0.amplitude)
        }
        return InterpretResult(reps: repEvents, phaseSegments: segments,
                               framePhases: framePhases)
    }

    // MARK: - extrema + rep detection (ported core)

    /// An alternating extremum of the smoothed signal.
    private struct Pivot {
        var frame: Int
        var value: Double
        var kind: Kind
        enum Kind { case min, max }
    }

    /// A detected rep with the frame indices needed to lock bands + emit.
    private struct DetectedRep {
        let index: Int
        let startFrame: Int   // opening extremum (a "low" for cycleFrom == .low)
        let peakFrame: Int    // the turn-around extremum (the "high")
        let endFrame: Int     // closing extremum (the next "low")
        let startSeconds: Double
        let endSeconds: Double
        let amplitude: Double
    }

    /// Strictly-alternating minima/maxima via a retracement (zig-zag) scan.
    /// Mirrors `_alternating_extrema` in rep.py. A reversal is only confirmed
    /// once the signal retraces by `delta` from the running extreme. `delta` is
    /// `prominenceFrac` of the full peak-to-peak range, floored by `minAmplitude`.
    private static func alternatingExtrema(_ smoothed: [Double], rep: ExtremaPairRep,
                                           sampleRateHz: Double) -> [Pivot] {
        let n = smoothed.count
        guard n > 0 else { return [] }
        let fullRange = (smoothed.max() ?? 0) - (smoothed.min() ?? 0)
        let delta = Swift.max(rep.minAmplitude, rep.prominenceFrac * fullRange)
        let minSep = Swift.max(1, Int((rep.minSeparationS * sampleRateHz).rounded()))

        var pivots: [Pivot] = []
        var curMin = smoothed[0], curMax = smoothed[0]
        var curMinI = 0, curMaxI = 0
        var direction = 0  // 0 = unknown, +1 = seeking a max, -1 = seeking a min

        func record(_ frame: Int, _ value: Double, _ kind: Pivot.Kind) {
            // Min separation: if too close to the previous pivot, keep the more
            // extreme of the two rather than recording a second pivot.
            if let last = pivots.last, frame - last.frame < minSep {
                if (kind == .max && value > last.value) || (kind == .min && value < last.value) {
                    pivots[pivots.count - 1] = Pivot(frame: frame, value: value, kind: kind)
                }
                return
            }
            pivots.append(Pivot(frame: frame, value: value, kind: kind))
        }

        for i in 1..<n {
            let v = smoothed[i]
            if v > curMax { curMax = v; curMaxI = i }
            if v < curMin { curMin = v; curMinI = i }
            if direction >= 0 && curMax - v >= delta {
                record(curMaxI, curMax, .max)
                direction = -1
                curMin = v; curMinI = i
            } else if direction <= 0 && v - curMin >= delta {
                record(curMinI, curMin, .min)
                direction = 1
                curMax = v; curMaxI = i
            }
        }

        // Close the final pending swing so the last rep isn't dropped: the
        // trailing hold never retraces, so the closing extremum is otherwise
        // never confirmed.
        if let last = pivots.last {
            if last.kind == .max && curMinI > last.frame && last.value - curMin >= delta {
                record(curMinI, curMin, .min)
            } else if last.kind == .min && curMaxI > last.frame && curMax - last.value >= delta {
                record(curMaxI, curMax, .max)
            }
        }
        return pivots
    }

    /// Pair alternating pivots into full cycles. Mirrors `_detect_reps`.
    /// `cycleFrom == .low` → a rep is a low→high→low triple (turns around a max);
    /// `.high` → high→low→high (turns around a min). Amplitude-gated by minAmplitude.
    private static func detectReps(_ pivots: [Pivot], smoothed: [Double],
                                   stream: SkeletonStream, rep: ExtremaPairRep) -> [DetectedRep] {
        let centerKind: Pivot.Kind = rep.cycleFrom == .low ? .max : .min
        var reps: [DetectedRep] = []
        guard pivots.count >= 3 else { return reps }
        for j in 1..<(pivots.count - 1) {
            let center = pivots[j]
            if center.kind != centerKind { continue }
            let opener = pivots[j - 1], closer = pivots[j + 1]
            let amplitude: Double
            if centerKind == .max {
                amplitude = center.value - Swift.min(opener.value, closer.value)
            } else {
                amplitude = Swift.max(opener.value, closer.value) - center.value
            }
            if amplitude < rep.minAmplitude { continue }
            reps.append(DetectedRep(
                index: reps.count,
                startFrame: opener.frame,
                peakFrame: center.frame,
                endFrame: closer.frame,
                startSeconds: stream.frames[opener.frame].tSeconds,
                endSeconds: stream.frames[closer.frame].tSeconds,
                amplitude: amplitude
            ))
        }
        return reps
    }

    /// Per-frame milliseconds since the last velocity sign change. Mirrors
    /// `_ms_since_sign_change`. `nil` until the first sign change is seen.
    static func msSinceSignChange(_ vel: [Double], sampleRateHz: Double) -> [Double?] {
        let dtMs = 1000.0 / sampleRateHz
        let dead = 1e-6
        var out: [Double?] = []
        out.reserveCapacity(vel.count)
        var lastSign = 0
        var framesSince: Int? = nil
        for v in vel {
            let s = v > dead ? 1 : (v < -dead ? -1 : 0)
            if s != 0 && lastSign != 0 && s != lastSign {
                framesSince = 0
            } else if framesSince != nil {
                framesSince! += 1
            }
            if s != 0 { lastSign = s }
            out.append(framesSince.map { Double($0) * dtMs })
        }
        return out
    }

    /// Collapse a per-frame phase list into contiguous PhaseSegments. Mirrors
    /// `coalesce_segments` in rep.py.
    static func coalesceSegments(_ framePhases: [PhaseLabel],
                                 stream: SkeletonStream) -> [PhaseSegment] {
        guard !framePhases.isEmpty else { return [] }
        var segments: [PhaseSegment] = []
        var startI = 0
        var cur = framePhases[0]
        for i in 1..<framePhases.count where framePhases[i] != cur {
            segments.append(PhaseSegment(
                label: cur,
                startSeconds: stream.frames[startI].tSeconds,
                endSeconds: stream.frames[i].tSeconds,
                startFrame: startI,
                endFrame: i - 1
            ))
            startI = i
            cur = framePhases[i]
        }
        segments.append(PhaseSegment(
            label: cur,
            startSeconds: stream.frames[startI].tSeconds,
            endSeconds: stream.frames[framePhases.count - 1].tSeconds,
            startFrame: startI,
            endFrame: framePhases.count - 1
        ))
        return segments
    }
}
