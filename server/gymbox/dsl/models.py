"""Pydantic models for the gymbox exercise DSL.

This module is the **source of truth** for the spec format (architecture.md §10).
The locked `db_curl` grammar:

  - signal source: `joint_axis` (MVP-α). Others reserved (§11.3).
  - smoothing: `savitzky_golay` (default), `gaussian`, `none`.
  - rep detection: `extrema_pair` (default), `velocity_zero_crossing` reserved.
  - phase rules: abs_v_lt/gt, direction toward_high/toward_low,
    sign_changed_within_ms, position_band low/mid/high with dynamic bounds.
  - phase labels first-match-wins, order matters:
    RESET -> ISO_LOADED -> ISO_UNLOADED -> CON -> ECC.

`ModelSpec` (§11.2) is reserved and null in MVP-α: when null the DSL interpreter
is the sole detector; the phone treats null as a no-op.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Enums / vocabularies
# ---------------------------------------------------------------------------


class PhaseLabel(str, Enum):
    """Rep-phase labels. Loaded/unloaded is defined by TARGET-MUSCLE tension,
    not external-weight presence (architecture.md §10)."""

    CON = "CON"                    # concentric — shortening under load
    ECC = "ECC"                    # eccentric — lengthening under load
    ISO_LOADED = "ISO_LOADED"      # hold, muscle lengthened & resisting (db_curl: bottom)
    ISO_UNLOADED = "ISO_UNLOADED"  # hold, muscle shortened, minimal tension (db_curl: top)
    RESET = "RESET"                # between-rep transition / not in a rep


# First-match-wins evaluation order. RESET is evaluated FIRST (architecture.md §10).
PHASE_EVAL_ORDER: tuple[PhaseLabel, ...] = (
    PhaseLabel.RESET,
    PhaseLabel.ISO_LOADED,
    PhaseLabel.ISO_UNLOADED,
    PhaseLabel.CON,
    PhaseLabel.ECC,
)


class SignalType(str, Enum):
    """Discriminated-union tag for signal sources (architecture.md §11.3).

    Only `joint_axis` is implemented in MVP-α. An interpreter that encounters
    an unknown signal type MUST reject the spec at parse time and fall back to
    the bundled spec (graceful degradation).
    """

    JOINT_AXIS = "joint_axis"              # implemented MVP-α
    JOINT_ANGLE = "joint_angle"            # reserved
    JOINT_DISTANCE = "joint_distance"      # reserved
    HAND_LANDMARK_AXIS = "hand_landmark_axis"  # reserved
    OBJECT_KEYPOINT = "object_keypoint"    # reserved
    IMU_AXIS = "imu_axis"                  # reserved
    COMPOSITE = "composite"                # reserved


class Axis(str, Enum):
    X = "x"
    Y = "y"


class SmoothingMethod(str, Enum):
    SAVITZKY_GOLAY = "savitzky_golay"  # MVP-α default
    GAUSSIAN = "gaussian"
    NONE = "none"


class RepMethod(str, Enum):
    EXTREMA_PAIR = "extrema_pair"                    # MVP-α default
    VELOCITY_ZERO_CROSSING = "velocity_zero_crossing"  # reserved


class PositionBand(str, Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Signal source
# ---------------------------------------------------------------------------


class JointAxisSignal(BaseModel):
    """Track one joint along one image axis. MVP-α's only implemented signal.

    The raw signal value at frame t is keypoints[joint].{axis}. For db_curl this
    is the wrist's vertical (y) position; smoothing + differentiation give the
    velocity used by rep/phase detection.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal[SignalType.JOINT_AXIS] = SignalType.JOINT_AXIS
    # Joint name from the keypoints registry, e.g. "right_wrist".
    joint: str
    axis: Axis
    # If true, the signal is negated so that "toward_high" always means the
    # direction of the concentric (lifting) movement regardless of image axis
    # orientation. (Image y grows downward; lifting decreases y.)
    invert: bool = True


# Discriminated union of all signal sources. Only JointAxisSignal is constructible
# in MVP-α; the others are intentionally absent until their interpreters exist.
SignalSpec = Annotated[JointAxisSignal, Field(discriminator="type")]


# ---------------------------------------------------------------------------
# Smoothing
# ---------------------------------------------------------------------------


class SavitzkyGolaySmoothing(BaseModel):
    """Savitzky-Golay smoothing. Introduces a half-window emission delay
    (architecture.md §4): rep/phase events emit ~half the window late."""

    model_config = ConfigDict(extra="forbid")

    method: Literal[SmoothingMethod.SAVITZKY_GOLAY] = SmoothingMethod.SAVITZKY_GOLAY
    # Odd window length in frames (7-9 @ 15 Hz in db_curl).
    window_frames: int = Field(7, ge=3)
    polyorder: int = Field(2, ge=1)

    @model_validator(mode="after")
    def _check(self) -> "SavitzkyGolaySmoothing":
        if self.window_frames % 2 == 0:
            raise ValueError("savitzky_golay window_frames must be odd")
        if self.polyorder >= self.window_frames:
            raise ValueError("polyorder must be < window_frames")
        return self


class GaussianSmoothing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal[SmoothingMethod.GAUSSIAN] = SmoothingMethod.GAUSSIAN
    sigma_frames: float = Field(1.5, gt=0)


class NoSmoothing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal[SmoothingMethod.NONE] = SmoothingMethod.NONE


SmoothingSpec = Annotated[
    SavitzkyGolaySmoothing | GaussianSmoothing | NoSmoothing,
    Field(discriminator="method"),
]


# ---------------------------------------------------------------------------
# Rep detection
# ---------------------------------------------------------------------------


class ExtremaPairRep(BaseModel):
    """Detect reps as alternating extrema (a low followed by a high, or the
    configured cycle). Position bands are derived dynamically from the first
    completed rep's amplitude (architecture.md §10).
    """

    model_config = ConfigDict(extra="forbid")

    method: Literal[RepMethod.EXTREMA_PAIR] = RepMethod.EXTREMA_PAIR
    # Minimum normalized peak-to-peak amplitude for a movement to count as a rep.
    # Guards against jitter being counted as reps before the dynamic band locks.
    min_amplitude: float = Field(0.08, gt=0)
    # Minimum seconds between successive detected extrema (debounce).
    min_separation_s: float = Field(0.25, gt=0)
    # Prominence (relative to amplitude) an extremum must have to be accepted.
    prominence_frac: float = Field(0.30, ge=0, le=1)
    # Which extremum opens a rep cycle. "low" = rep starts at the bottom
    # (extended arm) for db_curl. (Forward-compat hook for inverted exercises
    # like pushdowns: set cycle_from="high".)
    cycle_from: Literal["low", "high"] = "low"


class VelocityZeroCrossingRep(BaseModel):
    """Reserved. Not implemented in MVP-α."""

    model_config = ConfigDict(extra="forbid")
    method: Literal[RepMethod.VELOCITY_ZERO_CROSSING] = RepMethod.VELOCITY_ZERO_CROSSING
    min_amplitude: float = Field(0.08, gt=0)


RepSpec = Annotated[
    ExtremaPairRep | VelocityZeroCrossingRep,
    Field(discriminator="method"),
]


# ---------------------------------------------------------------------------
# Phase rules
# ---------------------------------------------------------------------------


class PhaseConditions(BaseModel):
    """Predicate over the (smoothed) signal at a frame. All present conditions
    are ANDed. Absent conditions are not evaluated.

    Position bands are dynamic: `low`/`mid`/`high` resolve against the bounds
    learned from the first completed rep (architecture.md §10), not fixed
    coordinates.
    """

    model_config = ConfigDict(extra="forbid")

    # Velocity magnitude thresholds (normalized units / s).
    abs_v_lt: float | None = Field(None, ge=0)
    abs_v_gt: float | None = Field(None, ge=0)
    # Movement direction along the (inverted) signal.
    direction: Literal["toward_high", "toward_low"] | None = None
    # True iff the velocity sign changed within the last N ms (transition guard).
    sign_changed_within_ms: float | None = Field(None, ge=0)
    # Dynamic position band the signal must currently occupy.
    position_band: PositionBand | None = None


class PhaseRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: PhaseLabel
    when: PhaseConditions


class PhaseSpec(BaseModel):
    """Ordered list of phase rules, first-match-wins. The interpreter MUST
    evaluate rules in PHASE_EVAL_ORDER (RESET first), regardless of authoring
    order, and apply the first rule whose conditions hold.
    """

    model_config = ConfigDict(extra="forbid")

    rules: list[PhaseRule]
    # Label assigned when no rule matches. Defaults to RESET.
    default: PhaseLabel = PhaseLabel.RESET

    @model_validator(mode="after")
    def _check_labels(self) -> "PhaseSpec":
        labels = {r.label for r in self.rules}
        unknown = labels - set(PhaseLabel)
        if unknown:
            raise ValueError(f"unknown phase labels: {unknown}")
        return self

    def ordered_rules(self) -> list[PhaseRule]:
        """Rules sorted into the canonical first-match-wins evaluation order."""
        order = {label: i for i, label in enumerate(PHASE_EVAL_ORDER)}
        return sorted(self.rules, key=lambda r: order.get(r.label, len(order)))


# ---------------------------------------------------------------------------
# Optional per-exercise model (reserved; null in MVP-α — architecture.md §11.2)
# ---------------------------------------------------------------------------


class ModelSpec(BaseModel):
    """Optional per-exercise model attached to a DSL spec. Null in MVP-α.

    When populated (MVP-β+), the interpreter feeds frames through the model and
    uses its output as an additional signal. The MVP-α phone code path checks
    `if model_spec is not None` and treats null as a no-op.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["onnx_classifier_head"]  # extensible later
    storage_url: str
    version: str
    sha256: str
    input_window_frames: int = 32
    input_stride_frames: int = 8
    confidence_threshold: float = 0.5


# ---------------------------------------------------------------------------
# Top-level exercise spec
# ---------------------------------------------------------------------------


class ExerciseSpec(BaseModel):
    """A complete exercise specification. Loading a spec via `ExerciseSpec(...)`
    is the validation step when authoring a new exercise (architecture.md §10).
    """

    model_config = ConfigDict(extra="forbid")

    # Stable identifier, e.g. "db_curl". Matches exercises.id and the spec filename.
    id: str
    display_name: str
    # Integer schema version for graceful degradation: phones supporting an
    # older schema_version ignore newer specs (product.md "Versioning").
    schema_version: int = 1

    signal: SignalSpec
    smoothing: SmoothingSpec
    rep: RepSpec
    phase: PhaseSpec

    # Reserved; null in MVP-α (§11.2).
    model_spec: ModelSpec | None = None

    @model_validator(mode="after")
    def _mvp_alpha_guards(self) -> "ExerciseSpec":
        # MVP-α only ships joint_axis + extrema_pair. Reject anything that would
        # require an unimplemented interpreter path so authoring errors surface
        # immediately rather than at runtime on the phone.
        if self.signal.type is not SignalType.JOINT_AXIS:
            raise ValueError(
                f"signal.type {self.signal.type!r} is reserved, not implemented in MVP-α"
            )
        return self
