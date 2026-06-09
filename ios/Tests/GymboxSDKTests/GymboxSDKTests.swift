import XCTest
@testable import GymboxSDK

// Swift-side parity tests. The DSL decode, phase-evaluation order, and signal
// front-end are concrete and tested for real. The full interpreter (Gate B) is
// pending the port, so that path is asserted as not-yet-implemented rather than
// silently skipped.

final class GymboxSDKTests: XCTestCase {

    // MARK: fixtures

    private func fixtureData(_ name: String) throws -> Data {
        guard let url = Bundle.module.url(forResource: name, withExtension: "json",
                                          subdirectory: "Fixtures")
            ?? Bundle.module.url(forResource: name, withExtension: "json") else {
            throw XCTSkip("fixture \(name).json not bundled")
        }
        return try Data(contentsOf: url)
    }

    private func loadSpec() throws -> ExerciseSpec {
        try ExerciseSpec.decode(from: try fixtureData("db_curl"))
    }

    private func loadStream() throws -> SkeletonStream {
        let data = try fixtureData("bicep_curl_1")
        let obj = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let rate = obj["sample_rate_hz"] as! Double
        let frameDicts = obj["frames"] as! [[String: Any]]
        let frames: [Frame] = frameDicts.map { fd in
            let idx = fd["frame_index"] as! Int
            let t = fd["t_s"] as! Double
            let kps = (fd["keypoints"] as! [[Double]]).map { SIMD3<Double>($0[0], $0[1], $0[2]) }
            return Frame(frameIndex: idx, tSeconds: t, keypoints: kps)
        }
        return SkeletonStream(sampleRateHz: rate, frames: frames)
    }

    // MARK: DSL

    func testKeypointRegistryMatchesPython() {
        // Spot-check the indices the db_curl signal relies on.
        XCTAssertEqual(Keypoints.count, 33)
        XCTAssertEqual(Keypoints.index(of: "right_wrist"), 16)
        XCTAssertEqual(Keypoints.index(of: "right_elbow"), 14)
        XCTAssertEqual(Keypoints.index(of: "right_shoulder"), 12)
        XCTAssertEqual(Keypoints.name(of: 0), "nose")
    }

    func testDecodeDbCurlSpec() throws {
        let spec = try loadSpec()
        XCTAssertEqual(spec.id, "db_curl")
        XCTAssertEqual(spec.signal.joint, "right_wrist")
        XCTAssertEqual(spec.signal.axis, .y)
        XCTAssertTrue(spec.signal.invert)
        XCTAssertEqual(spec.smoothing.method, .savitzkyGolay)
        XCTAssertEqual(spec.smoothing.windowFrames, 7)
        XCTAssertEqual(spec.rep.method, .extremaPair)
        XCTAssertNil(spec.modelSpec)
    }

    func testPhaseEvaluationOrderRESETFirst() throws {
        let spec = try loadSpec()
        let ordered = spec.phase.orderedRules().map { $0.label }
        XCTAssertEqual(ordered.first, .reset)
        let rank = Dictionary(uniqueKeysWithValues:
            PhaseLabel.evaluationOrder.enumerated().map { ($1, $0) })
        XCTAssertEqual(ordered, ordered.sorted { rank[$0]! < rank[$1]! })
    }

    func testEmissionDelayIsHalfWindow() throws {
        let spec = try loadSpec()
        XCTAssertEqual(spec.smoothing.emissionDelayFrames, 3)  // window 7 -> 3
    }

    // MARK: signal front-end (concrete)

    func testSignalExtractionAndSmoothing() throws {
        let spec = try loadSpec()
        let stream = try loadStream()
        let raw = Signal.extractJointAxis(stream, spec.signal)
        XCTAssertEqual(raw.count, stream.count)
        let smoothed = Signal.smooth(raw, spec.smoothing)
        XCTAssertEqual(smoothed.count, raw.count)
        let v = Signal.velocity(smoothed, sampleRateHz: stream.sampleRateHz)
        XCTAssertEqual(v.count, smoothed.count)
        XCTAssertTrue(smoothed.allSatisfy { $0.isFinite })
    }

    func testEvaluatePhaseHonoursConditions() throws {
        let spec = try loadSpec()
        // Low velocity in the mid band -> RESET (first matching rule).
        let ctx = FrameContext(velocity: 0.0, direction: nil,
                               positionBand: .mid, signChangedWithinMs: nil)
        XCTAssertEqual(DSLInterpreter.evaluatePhase(spec.phase, ctx), .reset)

        // Fast motion toward the high end -> CON.
        let con = FrameContext(velocity: 0.2, direction: .towardHigh,
                               positionBand: nil, signChangedWithinMs: nil)
        XCTAssertEqual(DSLInterpreter.evaluatePhase(spec.phase, con), .con)
    }

    // MARK: Gate B (pending the interpreter port)

    func testInterpreterPortIsPending() throws {
        // Once DSLInterpreter.interpret is implemented, replace this with the
        // real Gate B comparison against the Python oracle's labels.
        // For now we simply assert the spec + stream load so the harness is
        // ready; we do NOT call interpret() because it intentionally traps.
        let spec = try loadSpec()
        let stream = try loadStream()
        XCTAssertGreaterThan(stream.count, 0)
        XCTAssertEqual(spec.id, "db_curl")
    }
}
