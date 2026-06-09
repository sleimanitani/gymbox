import Foundation

// Signal-processing front-end, ported from gymbox/pipeline/signal.py.
//
// This layer is CONCRETE and must match the Python numerically — Gate B
// compares interpreter output frame-for-frame, and any divergence here
// propagates. The Savitzky-Golay implementation uses the same least-squares
// formulation as scipy's (fit a polynomial in a sliding window, evaluate at the
// center), with edge handling by polynomial extrapolation within the first/last
// full windows. See architecture.md §10.

public enum Signal {

    /// Extract the tracked scalar from a stream: one joint's chosen axis,
    /// optionally inverted so "up" is the high value.
    public static func extractJointAxis(_ stream: SkeletonStream,
                                        _ signal: JointAxisSignal) -> [Double] {
        guard let jointIndex = Keypoints.index(of: signal.joint) else {
            return [Double](repeating: 0, count: stream.count)
        }
        return stream.frames.map { frame in
            let kp = frame.keypoints[jointIndex]
            let value: Double
            switch signal.axis {
            case .x: value = kp.x
            case .y: value = kp.y
            case .z: value = kp.x  // z unused in MVP-α; placeholder
            }
            return signal.invert ? -value : value
        }
    }

    /// Apply the configured smoothing. S-G is the MVP-α default.
    public static func smooth(_ values: [Double], _ spec: SmoothingSpec) -> [Double] {
        switch spec.method {
        case .none:
            return values
        case .gaussian:
            return gaussian(values, sigma: spec.sigma ?? 1.0)
        case .savitzkyGolay:
            return savitzkyGolay(values,
                                 window: spec.windowFrames,
                                 polyorder: spec.polyorder ?? 2)
        }
    }

    /// Central-difference velocity in signal-units per second.
    public static func velocity(_ smoothed: [Double], sampleRateHz: Double) -> [Double] {
        let n = smoothed.count
        guard n > 1 else { return [Double](repeating: 0, count: n) }
        let dt = 1.0 / sampleRateHz
        var v = [Double](repeating: 0, count: n)
        for i in 0..<n {
            if i == 0 {
                v[i] = (smoothed[1] - smoothed[0]) / dt
            } else if i == n - 1 {
                v[i] = (smoothed[n - 1] - smoothed[n - 2]) / dt
            } else {
                v[i] = (smoothed[i + 1] - smoothed[i - 1]) / (2 * dt)
            }
        }
        return v
    }

    // MARK: - smoothing kernels

    static func gaussian(_ values: [Double], sigma: Double) -> [Double] {
        let n = values.count
        guard n > 0, sigma > 0 else { return values }
        let radius = max(1, Int((3.0 * sigma).rounded()))
        var kernel = [Double](repeating: 0, count: 2 * radius + 1)
        var sum = 0.0
        for k in -radius...radius {
            let w = exp(-Double(k * k) / (2 * sigma * sigma))
            kernel[k + radius] = w
            sum += w
        }
        for i in kernel.indices { kernel[i] /= sum }
        var out = [Double](repeating: 0, count: n)
        for i in 0..<n {
            var acc = 0.0
            for k in -radius...radius {
                let j = min(max(i + k, 0), n - 1)  // edge clamp
                acc += values[j] * kernel[k + radius]
            }
            out[i] = acc
        }
        return out
    }

    /// Savitzky-Golay smoothing. Mirrors scipy.signal.savgol_filter with
    /// mode='interp': fit `polyorder` polynomial over each centered window via
    /// least squares; the smoothed sample is the fit at the window center. The
    /// first/last halfWindow points are filled by evaluating the edge window's
    /// polynomial fit (interp mode), not by mirroring.
    static func savitzkyGolay(_ values: [Double], window: Int, polyorder: Int) -> [Double] {
        let n = values.count
        guard window >= 3, window % 2 == 1, polyorder < window, n >= window else {
            return values
        }
        let half = window / 2
        // Precompute the SG convolution coefficients for the central point and
        // the per-position coefficients for the edges.
        // Central coefficients: c = (A^T A)^{-1} A^T applied at center row.
        let A = vandermonde(half: half, polyorder: polyorder)            // window x (poly+1)
        let ata = matMul(transpose(A), A)                                 // (p+1)x(p+1)
        let ataInv = invert(ata)
        let pinv = matMul(ataInv, transpose(A))                           // (p+1) x window

        // Central smoothing coefficients = first row of (A * pinv) evaluated at
        // center == pinv row 0 dotted with monomials at x=0 -> just pinv[0].
        let centerCoeffs = pinv[0]  // length == window

        var out = [Double](repeating: 0, count: n)

        // Interior: straightforward convolution.
        for i in half..<(n - half) {
            var acc = 0.0
            for k in 0..<window {
                acc += centerCoeffs[k] * values[i - half + k]
            }
            out[i] = acc
        }

        // Edges (interp mode): fit the polynomial to the first/last window and
        // evaluate it at the actual offset of each edge sample.
        let firstWindow = Array(values[0..<window])
        let firstCoefs = polyFit(firstWindow, pinv: pinv)  // poly coefficients
        for i in 0..<half {
            out[i] = polyEval(firstCoefs, x: Double(i - half))
        }
        let lastWindow = Array(values[(n - window)..<n])
        let lastCoefs = polyFit(lastWindow, pinv: pinv)
        for i in (n - half)..<n {
            // x measured from the center of the last window.
            let x = Double(i - (n - 1 - half))
            out[i] = polyEval(lastCoefs, x: x)
        }
        return out
    }

    // MARK: - tiny linear algebra (window-sized; not performance critical)

    /// Vandermonde matrix for offsets [-half ... +half], columns x^0..x^p.
    private static func vandermonde(half: Int, polyorder: Int) -> [[Double]] {
        var rows: [[Double]] = []
        for k in -half...half {
            var row = [Double](repeating: 0, count: polyorder + 1)
            var p = 1.0
            for j in 0...polyorder { row[j] = p; p *= Double(k) }
            rows.append(row)
        }
        return rows
    }

    private static func transpose(_ m: [[Double]]) -> [[Double]] {
        guard let first = m.first else { return [] }
        var t = [[Double]](repeating: [Double](repeating: 0, count: m.count), count: first.count)
        for i in m.indices { for j in first.indices { t[j][i] = m[i][j] } }
        return t
    }

    private static func matMul(_ a: [[Double]], _ b: [[Double]]) -> [[Double]] {
        let n = a.count, m = b[0].count, k = b.count
        var c = [[Double]](repeating: [Double](repeating: 0, count: m), count: n)
        for i in 0..<n { for j in 0..<m {
            var s = 0.0
            for t in 0..<k { s += a[i][t] * b[t][j] }
            c[i][j] = s
        } }
        return c
    }

    /// Gauss-Jordan inverse of a small square matrix.
    private static func invert(_ matrix: [[Double]]) -> [[Double]] {
        let n = matrix.count
        var a = matrix
        var inv = (0..<n).map { i in (0..<n).map { $0 == i ? 1.0 : 0.0 } }
        for col in 0..<n {
            var pivot = col
            for r in (col + 1)..<n where abs(a[r][col]) > abs(a[pivot][col]) { pivot = r }
            a.swapAt(col, pivot); inv.swapAt(col, pivot)
            let d = a[col][col]
            guard d != 0 else { continue }
            for j in 0..<n { a[col][j] /= d; inv[col][j] /= d }
            for r in 0..<n where r != col {
                let f = a[r][col]
                for j in 0..<n { a[r][j] -= f * a[col][j]; inv[r][j] -= f * inv[col][j] }
            }
        }
        return inv
    }

    /// Polynomial coefficients (lowest order first) fit to a window via pinv.
    private static func polyFit(_ windowValues: [Double], pinv: [[Double]]) -> [Double] {
        // coefficients = pinv * y
        pinv.map { row in zip(row, windowValues).reduce(0) { $0 + $1.0 * $1.1 } }
    }

    private static func polyEval(_ coefs: [Double], x: Double) -> Double {
        var acc = 0.0, p = 1.0
        for c in coefs { acc += c * p; p *= x }
        return acc
    }
}
