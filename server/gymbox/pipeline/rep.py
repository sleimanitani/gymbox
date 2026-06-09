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
from .types import InterpretResult, SkeletonStream


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

    # --- detection core (IMPLEMENT) ---------------------------------------
    #
    # Steps (see module docstring):
    #   1. Detect extrema on `smoothed`; pair into reps per spec.rep.
    #   2. bands.fit_from_rep(min, max) from the first completed rep.
    #   3. For each frame i, build FrameContext from vel[i], direction, band,
    #      and sign-change recency; phase = evaluate_phase(spec.phase, ctx).
    #   4. Coalesce frame phases into PhaseSegments; assemble InterpretResult.
    #
    # Until implemented, fail loudly so Gate A clearly reports "not done yet".
    raise NotImplementedError(
        "pipeline.rep.interpret: implement extrema_pair rep detection + per-frame "
        "phase labeling (ROADMAP Step 3). Front-end (signal/smoothing/velocity) and "
        "evaluate_phase() are already provided. Target: Gate A on bicep_curl_1 "
        "(rep error ≤1, phase agreement ≥85%)."
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
