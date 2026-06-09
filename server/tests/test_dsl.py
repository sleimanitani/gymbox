"""DSL model tests: round-trip, MVP-α validation guards, phase eval order.

These are pure-unit and have no DB/IO dependency. They lock the D6 grammar
(architecture.md §10) so the Swift port (Gate B) has an unambiguous reference.
"""
from __future__ import annotations

import pytest

from gymbox.dsl import PhaseLabel, load_spec, load_spec_dict
from gymbox.dsl.models import PHASE_EVAL_ORDER, ExerciseSpec


def test_db_curl_loads(db_curl_spec: ExerciseSpec) -> None:
    assert db_curl_spec.id == "db_curl"
    assert db_curl_spec.signal.type == "joint_axis"
    assert db_curl_spec.signal.joint == "right_wrist"
    assert db_curl_spec.signal.axis == "y"
    assert db_curl_spec.signal.invert is True
    # MVP-α ships no learned model.
    assert db_curl_spec.model_spec is None


def test_db_curl_round_trips(db_curl_spec: ExerciseSpec) -> None:
    """Spec -> dict -> spec must be a fixed point (OTA channel integrity)."""
    as_dict = db_curl_spec.model_dump(mode="json", exclude_none=True)
    again = load_spec_dict(as_dict)
    assert again.model_dump(mode="json", exclude_none=True) == as_dict


def test_phase_rules_reorder_to_eval_order(db_curl_spec: ExerciseSpec) -> None:
    """Whatever the authoring order, ordered_rules() yields PHASE_EVAL_ORDER.

    RESET must come first (architecture.md §10, first-match-wins).
    """
    ordered = db_curl_spec.phase.ordered_rules()
    seen = [r.label for r in ordered]
    rank = {lbl: i for i, lbl in enumerate(PHASE_EVAL_ORDER)}
    assert seen == sorted(seen, key=lambda l: rank[l])
    assert seen[0] == PhaseLabel.RESET


def test_eval_order_constant_is_canonical() -> None:
    assert PHASE_EVAL_ORDER == (
        PhaseLabel.RESET,
        PhaseLabel.ISO_LOADED,
        PhaseLabel.ISO_UNLOADED,
        PhaseLabel.CON,
        PhaseLabel.ECC,
    )


def test_non_joint_axis_signal_rejected() -> None:
    """MVP-α guard: only joint_axis is a legal signal source."""
    bad = {
        "id": "x",
        "display_name": "x",
        "schema_version": 1,
        "signal": {"type": "joint_angle", "joint": "right_elbow"},
        "smoothing": {"method": "savitzky_golay", "window_frames": 7, "polyorder": 2},
        "rep": {"method": "extrema_pair", "min_amplitude": 0.08,
                "min_separation_s": 0.25, "prominence_frac": 0.3, "cycle_from": "low"},
        "phase": {"default": "RESET", "rules": []},
    }
    with pytest.raises(Exception):
        load_spec_dict(bad)


def test_savgol_window_must_be_odd() -> None:
    bad = {
        "id": "x",
        "display_name": "x",
        "schema_version": 1,
        "signal": {"type": "joint_axis", "joint": "right_wrist", "axis": "y"},
        "smoothing": {"method": "savitzky_golay", "window_frames": 6, "polyorder": 2},
        "rep": {"method": "extrema_pair", "min_amplitude": 0.08,
                "min_separation_s": 0.25, "prominence_frac": 0.3, "cycle_from": "low"},
        "phase": {"default": "RESET", "rules": []},
    }
    with pytest.raises(Exception):
        load_spec_dict(bad)
