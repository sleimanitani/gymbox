"""gymbox DSL package.

Exposes the spec models and a loader that validates JSON specs into typed
`ExerciseSpec` instances (the authoring validation step, architecture.md §10).
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import (
    Axis,
    ExerciseSpec,
    ExtremaPairRep,
    GaussianSmoothing,
    JointAxisSignal,
    ModelSpec,
    NoSmoothing,
    PHASE_EVAL_ORDER,
    PhaseConditions,
    PhaseLabel,
    PhaseRule,
    PhaseSpec,
    PositionBand,
    RepMethod,
    SavitzkyGolaySmoothing,
    SignalType,
    SmoothingMethod,
)

__all__ = [
    "Axis",
    "ExerciseSpec",
    "ExtremaPairRep",
    "GaussianSmoothing",
    "JointAxisSignal",
    "ModelSpec",
    "NoSmoothing",
    "PHASE_EVAL_ORDER",
    "PhaseConditions",
    "PhaseLabel",
    "PhaseRule",
    "PhaseSpec",
    "PositionBand",
    "RepMethod",
    "SavitzkyGolaySmoothing",
    "SignalType",
    "SmoothingMethod",
    "load_spec",
    "load_spec_dict",
]


def load_spec_dict(data: dict) -> ExerciseSpec:
    """Validate a spec given as a dict into a typed ExerciseSpec."""
    return ExerciseSpec.model_validate(data)


def load_spec(path: str | Path) -> ExerciseSpec:
    """Load and validate an ExerciseSpec from a JSON file on disk."""
    text = Path(path).read_text(encoding="utf-8")
    return load_spec_dict(json.loads(text))
