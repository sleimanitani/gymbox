"""Reference DSL interpreter — rep + phase detection.

============================================================================
ROADMAP STEP 3 — THE FIRST MVP-α MILESTONE.
============================================================================

This is the Python golden oracle. Implement `interpret()` so it runs the locked
DSL grammar (db_curl) against a skeleton stream and produces reps + per-frame
phase labels.

ACCEPTANCE — GATE A (architecture.md §10):
  Run this interpreter against the human-labelled `bicep_curl_1` fixture
  (tests/fixtures/bicep_curl_1.json). Required:
    * rep-count error ≤ 1
    * frame-level phase agreement ≥ 85%
  A failure here is a SPEC/TUNING problem (thresholds/bands/smoothing in
  db_curl.json), not a code problem — but the code must be correct enough to
  expose that. Gate A must pass BEFORE the Swift port (Gate B) is meaningful.

WHAT IS ALREADY DONE FOR YOU:
  * Signal extraction + Savitzky-Golay smoothing + velocity: pipeline/signal.py
  * Phase-rule evaluation (first-match-wins, RESET first): `evaluate_phase()`
    below is COMPLETE and locked — call it per frame.
  * Dynamic position-band resolution scaffolding: `DynamicBands` below.
  * Result containers: pipeline/types.py
  * Metrics + fixture loading: pipeline/metrics.py, tests/conftest helpers.

WHAT YOU MUST IMPLEMENT (the `NotImplementedError` below):
  1. Rep detection via `extrema_pair` over the smoothed signal:
       - find alternating extrema (minima/maxima) with prominence/separation
         per rep_spec (min_amplitude, min_separation_s, prominence_frac, cycle_from)
       - a rep is one full cycle (low->high->low for cycle_from="low")
       - emit RepEvent(index, start_s, end_s, amplitude)
  2. Lock the dynamic position bands from the FIRST completed rep's amplitude
     (use `DynamicBands.fit_from_rep`), then resolve each frame's band.
  3. Per-frame phase labeling: for every frame, build a `FrameContext` and call
     `evaluate_phase(spec.phase, ctx)`. Collect into `frame_phases`, then
     coalesce into `PhaseSegment`s.
  4. Respect the Savitzky-Golay emission delay (signal.emission_delay_frames):
     reps/phases are known only after the half-window lookahead. For the OFFLINE
     oracle you may label all frames (full lookahead available); just keep the
     delay in mind for Gate B parity with the streaming Swift port.

DO NOT:
  * add a learned classifier (MVP-α is heuristic-only)
  * change the DSL grammar or db_curl.json to make a bug pass (fix the code; only
    retune the spec if Gate A fails for genuine tuning reasons)
  * import torch / onnxruntime here — this module is pure NumPy
============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..dsl.models import (
    ExerciseSpec,
    ExtremaPairRep,
    PhaseConditions,
    PhaseLabel,
    PhaseSpec,
    PositionBand,
)
from . import signal as sig
from .types import InterpretResult, RepEvent, SkeletonStream


# ---------------------------------------------------------------------------
# Dynamic position bands (architecture.md §10) — scaffolding provided.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DynamicBands:
    """Resolves low/mid/high position bands from the first completed rep.

    The bands are fractions of the first rep's amplitude. `low` is near the
    bottom (extended arm, ISO_LOADED), `high` near the top (flexed, ISO_UNLOADED),
    `mid` the transition zone. Until the first rep completes, `ready` is False
    and `band_of` returns None (no ISO/RESET position labeling yet).
    """

    low_max: float | None = None   # signal <= low_max  -> LOW band
    high_min: float | None = None  # signal >= high_min -> HIGH band
    # (mid is the open interval between low_max and high_min)
    ready: bool = False

    # Fraction of amplitude used as the band margin around each extreme.
    band_frac: float = 0.25

    def fit_from_rep(self, signal_min: float, signal_max: float) -> None:
        """Lock the bands from the first rep's observed min/max signal values."""
        amp = signal_max - signal_min
        margin = amp * self.band_frac
        self.low_max = signal_min + margin
        self.high_min = signal_max - margin
        self.ready = True

    def band_of(self, value: float) -> PositionBand | None:
        if not self.ready:
            return None
        assert self.low_max is not None and self.high_min is not None
        if value <= self.low_max:
            return PositionBand.LOW
        if value >= self.high_min:
            return PositionBand.HIGH
        return PositionBand.MID


# ---------------------------------------------------------------------------
# Per-frame context + phase evaluation (COMPLETE / LOCKED — call this).
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FrameContext:
    """Everything a phase rule may inspect for a single frame."""

    abs_v: float                       # |velocity|
    direction: str | None              # "toward_high" | "toward_low" | None (still)
    position_band: PositionBand | None  # from DynamicBands.band_of, or None pre-lock
    sign_changed_within_ms: float | None  # ms since last velocity sign change, or None


def _condition_holds(cond: PhaseConditions, ctx: FrameContext) -> bool:
    """True iff all present conditions in `cond` are satisfied by `ctx`. ANDed."""
    if cond.abs_v_lt is not None and not (ctx.abs_v < cond.abs_v_lt):
        return False
    if cond.abs_v_gt is not None and not (ctx.abs_v > cond.abs_v_gt):
        return False
    if cond.direction is not None and ctx.direction != cond.direction:
        return False
    if cond.position_band is not None and ctx.position_band != cond.position_band:
        return False
    if cond.sign_changed_within_ms is not None:
        if ctx.sign_changed_within_ms is None:
            return False
        if not (ctx.sign_changed_within_ms <= cond.sign_changed_within_ms):
            return False
    return True


def evaluate_phase(phase_spec: PhaseSpec, ctx: FrameContext) -> PhaseLabel:
    """First-match-wins phase evaluation in canonical order (RESET first).

    COMPLETE and locked (architecture.md §10). The interpreter must call this
    once per frame. Rules are evaluated in PHASE_EVAL_ORDER regardless of
    authoring order; the first whose conditions hold wins; otherwise `default`.
    """
    for rule in phase_spec.ordered_rules():
        if _condition_holds(rule.when, ctx):
            return rule.label
    return phase_spec.default


# ---------------------------------------------------------------------------
# The interpreter (IMPLEMENT THIS).
# ---------------------------------------------------------------------------


def interpret(spec: ExerciseSpec, stream: SkeletonStream) -> InterpretResult:
    """Run the DSL interpreter over a skeleton stream.

    See the module docstring for the full contract. The signal-processing
    front-end is wired below; the detection core raises NotImplementedError.
    """
    if not isinstance(spec.rep, ExtremaPairRep):
        raise NotImplementedError(
            f"rep method {spec.rep.method!r} not implemented in MVP-α (only extrema_pair)"
        )

    # --- front-end (provided) ---------------------------------------------
    raw = sig.extract_joint_axis(stream, spec.signal)
    smoothed = sig.smooth(raw, spec.smoothing)
    vel = sig.velocity(smoothed, stream.sample_rate_hz)
    _delay = sig.emission_delay_frames(spec.smoothing)  # noqa: F841 (Gate B parity)

    bands = DynamicBands(band_frac=0.25)

    # --- detection core ---------------------------------------------------
    # 1. Alternating extrema (pivots) over the smoothed signal.
    pivots = _alternating_extrema(smoothed, spec.rep, stream.sample_rate_hz)

    # 2. Pair pivots into reps; lock the dynamic bands from the FIRST rep.
    reps = _detect_reps(pivots, smoothed, stream, spec.rep)
    if reps:
        first = reps[0]
        lo = min(smoothed[first.start_frame], smoothed[first.end_frame])
        hi = smoothed[first.peak_frame]
        bands.fit_from_rep(signal_min=float(lo), signal_max=float(hi))

    # 3. Per-frame phase labeling. The offline oracle has full lookahead, so
    #    the bands locked from the first rep are applied to ALL frames (the
    #    emission delay only matters for the streaming Swift port — Gate B).
    sign_change_ms = _ms_since_sign_change(vel, stream.sample_rate_hz)
    frame_phases: list[PhaseLabel] = []
    for i in range(len(stream)):
        ctx = FrameContext(
            abs_v=abs(float(vel[i])),
            direction=direction_label(float(vel[i])),
            position_band=bands.band_of(float(smoothed[i])),
            sign_changed_within_ms=sign_change_ms[i],
        )
        frame_phases.append(evaluate_phase(spec.phase, ctx))

    # 4. Coalesce into segments and assemble the result.
    segments = coalesce_segments(frame_phases, stream)
    rep_events = [
        RepEvent(index=r.index, start_s=r.start_s, end_s=r.end_s, amplitude=r.amplitude)
        for r in reps
    ]
    return InterpretResult(
        reps=rep_events, phase_segments=segments, frame_phases=frame_phases
    )


# ---------------------------------------------------------------------------
# Helpers the implementation will likely want (provided, optional to use).
# ---------------------------------------------------------------------------


def direction_label(v: float, dead_zone: float = 1e-6) -> str | None:
    """Map a velocity to a movement direction along the (inverted) signal."""
    if v > dead_zone:
        return "toward_high"
    if v < -dead_zone:
        return "toward_low"
    return None


# ---------------------------------------------------------------------------
# Extrema + rep detection (the implemented core).
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Pivot:
    """An alternating extremum of the smoothed signal."""

    frame: int
    value: float
    kind: str  # "min" | "max"


@dataclass(slots=True)
class _Rep:
    """A detected rep with the frame indices needed to lock bands + emit."""

    index: int
    start_frame: int   # opening extremum (a "low" for cycle_from="low")
    peak_frame: int    # the turn-around extremum (the "high")
    end_frame: int     # closing extremum (the next "low")
    start_s: float
    end_s: float
    amplitude: float


def _alternating_extrema(
    smoothed: np.ndarray, rep_spec: ExtremaPairRep, sample_rate_hz: float
) -> list[_Pivot]:
    """Find strictly-alternating minima/maxima via a retracement (zig-zag) scan.

    A reversal is only confirmed once the signal retraces by `delta` from the
    running extreme, which rejects jitter and the slow drift inside ISO holds.
    `delta` is `prominence_frac` of the signal's full peak-to-peak range, floored
    by `min_amplitude` so a tiny global range can't make `delta` collapse to ~0.
    Pure NumPy — no scipy — so it ports cleanly to Swift for Gate B.
    """
    n = len(smoothed)
    if n == 0:
        return []
    full_range = float(smoothed.max() - smoothed.min())
    delta = max(rep_spec.min_amplitude, rep_spec.prominence_frac * full_range)
    min_sep = max(1, int(round(rep_spec.min_separation_s * sample_rate_hz)))

    pivots: list[_Pivot] = []
    cur_min = cur_max = float(smoothed[0])
    cur_min_i = cur_max_i = 0
    direction = 0  # 0 = unknown, +1 = seeking a max, -1 = seeking a min

    def _record(frame: int, value: float, kind: str) -> None:
        # Enforce min separation: if too close to the previous pivot, keep the
        # more extreme of the two rather than recording a second pivot.
        if pivots and frame - pivots[-1].frame < min_sep:
            prev = pivots[-1]
            if (kind == "max" and value > prev.value) or (
                kind == "min" and value < prev.value
            ):
                prev.frame, prev.value, prev.kind = frame, value, kind
            return
        pivots.append(_Pivot(frame=frame, value=value, kind=kind))

    for i in range(1, n):
        v = float(smoothed[i])
        if v > cur_max:
            cur_max, cur_max_i = v, i
        if v < cur_min:
            cur_min, cur_min_i = v, i
        if direction >= 0 and cur_max - v >= delta:
            _record(cur_max_i, cur_max, "max")
            direction = -1
            cur_min, cur_min_i = v, i
        elif direction <= 0 and v - cur_min >= delta:
            _record(cur_min_i, cur_min, "min")
            direction = 1
            cur_max, cur_max_i = v, i

    # Close the final pending swing so the last rep isn't dropped: the trailing
    # hold never retraces, so the closing extremum is otherwise never confirmed.
    if pivots:
        last = pivots[-1]
        if last.kind == "max" and cur_min_i > last.frame and last.value - cur_min >= delta:
            _record(cur_min_i, cur_min, "min")
        elif last.kind == "min" and cur_max_i > last.frame and cur_max - last.value >= delta:
            _record(cur_max_i, cur_max, "max")
    return pivots


def _detect_reps(
    pivots: list[_Pivot],
    smoothed: np.ndarray,
    stream: SkeletonStream,
    rep_spec: ExtremaPairRep,
) -> list[_Rep]:
    """Pair alternating pivots into full cycles.

    For `cycle_from="low"` a rep is a low→high→low triple (the cycle turns around
    a maximum); for `"high"` it is high→low→high (turns around a minimum). The
    peak-to-peak amplitude must clear `min_amplitude` for the cycle to count.
    """
    center_kind = "max" if rep_spec.cycle_from == "low" else "min"
    reps: list[_Rep] = []
    for j in range(1, len(pivots) - 1):
        center = pivots[j]
        if center.kind != center_kind:
            continue
        opener, closer = pivots[j - 1], pivots[j + 1]
        if center_kind == "max":
            amplitude = center.value - min(opener.value, closer.value)
        else:
            amplitude = max(opener.value, closer.value) - center.value
        if amplitude < rep_spec.min_amplitude:
            continue
        reps.append(
            _Rep(
                index=len(reps),
                start_frame=opener.frame,
                peak_frame=center.frame,
                end_frame=closer.frame,
                start_s=stream.frames[opener.frame].t_s,
                end_s=stream.frames[closer.frame].t_s,
                amplitude=float(amplitude),
            )
        )
    return reps


def _ms_since_sign_change(vel: np.ndarray, sample_rate_hz: float) -> list[float | None]:
    """Per-frame milliseconds since the last velocity sign change.

    Used to populate `FrameContext.sign_changed_within_ms` (a transition guard
    some specs reference). `None` until the first sign change is seen. A dead
    zone keeps near-zero ISO-hold noise from registering as crossings.
    """
    dt_ms = 1000.0 / sample_rate_hz
    dead = 1e-6
    out: list[float | None] = []
    last_sign = 0
    frames_since: int | None = None
    for v in vel:
        s = 1 if v > dead else (-1 if v < -dead else 0)
        if s != 0 and last_sign != 0 and s != last_sign:
            frames_since = 0
        elif frames_since is not None:
            frames_since += 1
        if s != 0:
            last_sign = s
        out.append(None if frames_since is None else frames_since * dt_ms)
    return out


def coalesce_segments(
    frame_phases: list[PhaseLabel], stream: SkeletonStream
) -> list:
    """Collapse a per-frame phase list into contiguous PhaseSegments."""
    from .types import PhaseSegment

    if not frame_phases:
        return []
    segments: list[PhaseSegment] = []
    start_i = 0
    cur = frame_phases[0]
    for i in range(1, len(frame_phases)):
        if frame_phases[i] != cur:
            segments.append(
                PhaseSegment(
                    label=cur,
                    start_s=stream.frames[start_i].t_s,
                    end_s=stream.frames[i].t_s,
                    start_frame=start_i,
                    end_frame=i - 1,
                )
            )
            start_i = i
            cur = frame_phases[i]
    segments.append(
        PhaseSegment(
            label=cur,
            start_s=stream.frames[start_i].t_s,
            end_s=stream.frames[-1].t_s,
            start_frame=start_i,
            end_frame=len(frame_phases) - 1,
        )
    )
    return segments
