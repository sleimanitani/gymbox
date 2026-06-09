"""Signal extraction + smoothing for the reference interpreter.

Concrete: extracts the 1-D signal the DSL's `joint_axis` source describes,
applies the configured smoothing, and computes velocity. The Savitzky-Golay
path is the MVP-α default and introduces a half-window emission delay
(architecture.md §3, §4) — documented here and surfaced via `emission_delay_frames`.

This module is the part of Step 3 that is mechanical and locked; the *detection*
logic that consumes its output (rep.py) is the open implementation work.
"""

from __future__ import annotations

import numpy as np

from ..dsl.keypoints import index_of
from ..dsl.models import (
    Axis,
    GaussianSmoothing,
    JointAxisSignal,
    NoSmoothing,
    SavitzkyGolaySmoothing,
    SmoothingSpec,
)
from .types import SkeletonStream


def extract_joint_axis(stream: SkeletonStream, signal: JointAxisSignal) -> np.ndarray:
    """Extract the raw 1-D signal for a joint_axis source.

    Returns a float array of length len(stream). If `invert` is set, the signal
    is negated so "toward_high" is the lifting direction regardless of image-axis
    orientation (image y grows downward).
    """
    jidx = index_of(signal.joint)
    axis_sel = 0 if signal.axis is Axis.X else 1
    raw = np.array(
        [f.keypoints[jidx][axis_sel] for f in stream.frames], dtype=np.float64
    )
    if signal.invert:
        raw = -raw
    return raw


def smooth(values: np.ndarray, spec: SmoothingSpec) -> np.ndarray:
    """Apply the configured smoothing to a 1-D signal."""
    if isinstance(spec, NoSmoothing):
        return values.copy()
    if isinstance(spec, GaussianSmoothing):
        return _gaussian(values, spec.sigma_frames)
    if isinstance(spec, SavitzkyGolaySmoothing):
        return _savitzky_golay(values, spec.window_frames, spec.polyorder)
    raise TypeError(f"unknown smoothing spec: {type(spec)!r}")  # pragma: no cover


def velocity(smoothed: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    """Central-difference velocity (normalized units / second)."""
    dt = 1.0 / sample_rate_hz
    return np.gradient(smoothed, dt)


def emission_delay_frames(spec: SmoothingSpec) -> int:
    """Frames of lookahead the smoothing introduces before an event can emit.

    For Savitzky-Golay this is half the window (architecture.md §4). This is the
    quantity the Swift port must match for rep-boundary timing to align within
    the ±2-frame Gate B tolerance.
    """
    if isinstance(spec, SavitzkyGolaySmoothing):
        return spec.window_frames // 2
    if isinstance(spec, GaussianSmoothing):
        return int(round(spec.sigma_frames))
    return 0


# -- smoothing kernels ------------------------------------------------------


def _gaussian(values: np.ndarray, sigma: float) -> np.ndarray:
    radius = max(1, int(round(3 * sigma)))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    kernel /= kernel.sum()
    return np.convolve(values, kernel, mode="same")


def _savitzky_golay(values: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    """Savitzky-Golay smoothing.

    Uses scipy if available (preferred — its coefficients are the reference the
    Swift port should match), else falls back to a NumPy least-squares
    implementation that produces equivalent interior coefficients.
    """
    if len(values) < window:
        # Too short to filter; return as-is (degenerate fixtures).
        return values.copy()
    try:
        from scipy.signal import savgol_filter  # type: ignore

        return savgol_filter(values, window_length=window, polyorder=polyorder)
    except ImportError:
        return _savgol_numpy(values, window, polyorder)


def _savgol_numpy(values: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    """NumPy fallback Savitzky-Golay (interior coefficients via pseudoinverse)."""
    half = window // 2
    # Design matrix for a polynomial fit over the window.
    j = np.arange(-half, half + 1)
    A = np.vander(j, polyorder + 1, increasing=True)
    # Smoothing coefficients = first row of (A^T A)^-1 A^T.
    coeffs = np.linalg.pinv(A)[0]
    # Pad with edge reflection so output length matches input.
    padded = np.pad(values, (half, half), mode="reflect")
    out = np.convolve(padded, coeffs[::-1], mode="valid")
    return out[: len(values)]
