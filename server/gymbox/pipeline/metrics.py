"""Validation metrics for Gate A and Gate B (architecture.md §10).

Concrete. Given an InterpretResult and a ground truth (human labels for Gate A,
or another InterpretResult for Gate B), compute:

  - rep-count error           |pred_reps - true_reps|
  - frame-level phase agreement  fraction of frames with identical phase label
  - rep-boundary deviation     max/mean |pred_boundary - true_boundary| in frames

Gate A bar: rep error ≤ 1, phase agreement ≥ 0.85.
Gate B bar: phase identity ≥ 0.98, identical rep count, boundaries within ±2 frames.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..dsl.models import PhaseLabel
from .types import InterpretResult


@dataclass(slots=True)
class GateReport:
    rep_count_pred: int
    rep_count_true: int
    rep_count_error: int
    frame_phase_agreement: float
    n_frames: int
    max_boundary_dev_frames: float | None = None
    mean_boundary_dev_frames: float | None = None

    def passes_gate_a(self) -> bool:
        return self.rep_count_error <= 1 and self.frame_phase_agreement >= 0.85

    def passes_gate_b(self) -> bool:
        if self.rep_count_error != 0:
            return False
        if self.frame_phase_agreement < 0.98:
            return False
        if self.max_boundary_dev_frames is None:
            return True
        return self.max_boundary_dev_frames <= 2


def frame_phase_agreement(
    pred: list[PhaseLabel], truth: list[PhaseLabel]
) -> tuple[float, int]:
    """Fraction of frames where labels match. Compares over the overlap length."""
    n = min(len(pred), len(truth))
    if n == 0:
        return (0.0, 0)
    matches = sum(1 for i in range(n) if pred[i] == truth[i])
    return (matches / n, n)


def rep_boundaries(result: InterpretResult) -> list[tuple[float, float]]:
    return [(r.start_s, r.end_s) for r in result.reps]


def boundary_deviation_frames(
    pred: InterpretResult, truth_boundaries: list[tuple[float, float]], sample_rate_hz: float
) -> tuple[float | None, float | None]:
    """Max/mean rep-boundary deviation in frames, matching reps in order.

    Compares the min(len) leading reps; extra/missing reps are out of scope for
    boundary timing (they're caught by the rep-count error).
    """
    pred_b = rep_boundaries(pred)
    n = min(len(pred_b), len(truth_boundaries))
    if n == 0:
        return (None, None)
    devs: list[float] = []
    for i in range(n):
        for p, t in zip(pred_b[i], truth_boundaries[i]):
            devs.append(abs(p - t) * sample_rate_hz)
    return (max(devs), sum(devs) / len(devs))


def score_gate_a(
    pred: InterpretResult,
    *,
    true_rep_count: int,
    true_frame_phases: list[PhaseLabel],
) -> GateReport:
    agreement, n = frame_phase_agreement(pred.frame_phases, true_frame_phases)
    return GateReport(
        rep_count_pred=pred.rep_count,
        rep_count_true=true_rep_count,
        rep_count_error=abs(pred.rep_count - true_rep_count),
        frame_phase_agreement=agreement,
        n_frames=n,
    )


def score_gate_b(
    pred: InterpretResult,
    reference: InterpretResult,
    *,
    sample_rate_hz: float,
) -> GateReport:
    agreement, n = frame_phase_agreement(pred.frame_phases, reference.frame_phases)
    max_dev, mean_dev = boundary_deviation_frames(
        pred, rep_boundaries(reference), sample_rate_hz
    )
    return GateReport(
        rep_count_pred=pred.rep_count,
        rep_count_true=reference.rep_count,
        rep_count_error=abs(pred.rep_count - reference.rep_count),
        frame_phase_agreement=agreement,
        n_frames=n,
        max_boundary_dev_frames=max_dev,
        mean_boundary_dev_frames=mean_dev,
    )
