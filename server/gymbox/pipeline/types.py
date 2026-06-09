"""Shared types for the reference pipeline.

Concrete, dependency-light containers used across the interpreter, the signal
extractor, and the test harness. These mirror the proto/JSON shapes but are
plain Python for easy use in batch tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..dsl.models import PhaseLabel


@dataclass(slots=True)
class Frame:
    """One pose frame: 33 (x, y, visibility) triples + timestamp."""

    frame_index: int
    t_s: float
    # 33 keypoints, each (x, y, visibility), normalized to [0, 1].
    keypoints: list[tuple[float, float, float]]

    def xy(self, joint_index: int) -> tuple[float, float]:
        x, y, _ = self.keypoints[joint_index]
        return (x, y)


@dataclass(slots=True)
class SkeletonStream:
    """A full session's pose stream."""

    sample_rate_hz: float
    frames: list[Frame]

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def duration_s(self) -> float:
        return self.frames[-1].t_s - self.frames[0].t_s if self.frames else 0.0


@dataclass(slots=True)
class RepEvent:
    """A detected repetition."""

    index: int          # 0-based rep number within the stream
    start_s: float
    end_s: float
    amplitude: float    # normalized peak-to-peak of the tracked signal


@dataclass(slots=True)
class PhaseSegment:
    """A contiguous span assigned a single phase label."""

    label: PhaseLabel
    start_s: float
    end_s: float
    start_frame: int
    end_frame: int


@dataclass(slots=True)
class InterpretResult:
    """The full output of running the DSL interpreter over a stream.

    `frame_phases` is the per-frame phase label (length == number of frames),
    used for the frame-level phase-agreement metric (Gate A / Gate B).
    """

    reps: list[RepEvent] = field(default_factory=list)
    phase_segments: list[PhaseSegment] = field(default_factory=list)
    frame_phases: list[PhaseLabel] = field(default_factory=list)

    @property
    def rep_count(self) -> int:
        return len(self.reps)
