"""Gate A — the first real milestone (ROADMAP Step 3).

Runs the Python reference oracle (pipeline.rep.interpret) against the labelled
bicep_curl_1 fixture and scores it:

    * rep-count error  <= 1
    * frame-level phase agreement >= 85%

Until pipeline/rep.py is implemented, interpret() raises NotImplementedError and
this test reports as xfail (expected failure) — so the suite stays green and the
gap is visible. Once implemented, the xfail simply stops triggering and this
becomes a hard gate.

IMPORTANT (architecture.md §12): if this fails *after* implementation, the first
move is to retune exercises/db_curl.json — NOT to weaken these thresholds or the
grammar. The thresholds below are the contract.
"""
from __future__ import annotations

import pytest

from gymbox.dsl.models import ExerciseSpec
from gymbox.pipeline.metrics import frame_phase_agreement, score_gate_a
from gymbox.pipeline.rep import interpret
from gymbox.pipeline.types import SkeletonStream

REP_COUNT_TOLERANCE = 1
PHASE_AGREEMENT_FLOOR = 0.85


def _interpret_or_xfail(spec: ExerciseSpec, stream: SkeletonStream):
    try:
        return interpret(spec, stream)
    except NotImplementedError:
        pytest.xfail("pipeline/rep.py not yet implemented (ROADMAP Step 3 / Gate A)")


def test_gate_a_rep_count(
    bicep_stream: SkeletonStream,
    db_curl_spec: ExerciseSpec,
    bicep_truth_rep_count: int,
) -> None:
    result = _interpret_or_xfail(db_curl_spec, bicep_stream)
    err = abs(result.rep_count - bicep_truth_rep_count)
    assert err <= REP_COUNT_TOLERANCE, (
        f"rep-count error {err} > {REP_COUNT_TOLERANCE} "
        f"(got {result.rep_count}, truth {bicep_truth_rep_count})"
    )


def test_gate_a_phase_agreement(
    bicep_stream: SkeletonStream,
    db_curl_spec: ExerciseSpec,
    bicep_truth_phases,
) -> None:
    result = _interpret_or_xfail(db_curl_spec, bicep_stream)
    agreement, _ = frame_phase_agreement(result.frame_phases, bicep_truth_phases)
    assert agreement >= PHASE_AGREEMENT_FLOOR, (
        f"phase agreement {agreement:.3f} < {PHASE_AGREEMENT_FLOOR}"
    )


def test_gate_a_report(
    bicep_stream: SkeletonStream,
    db_curl_spec: ExerciseSpec,
    bicep_truth_phases,
    bicep_truth_rep_count: int,
) -> None:
    """End-to-end Gate A scoring via the metrics helper."""
    result = _interpret_or_xfail(db_curl_spec, bicep_stream)
    report = score_gate_a(
        result,
        true_rep_count=bicep_truth_rep_count,
        true_frame_phases=bicep_truth_phases,
    )
    assert report.passes_gate_a(), f"Gate A failed: {report}"
