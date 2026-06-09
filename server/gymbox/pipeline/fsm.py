"""Session/set finite-state machine (architecture.md §5).

ROADMAP: later step. Reference implementation of set boundary detection and the
session state machine used during batch replay / labeling. The phone runs the
Swift equivalent; this is the oracle.
"""

from __future__ import annotations

from .types import InterpretResult, SkeletonStream


def segment_sets(stream: SkeletonStream, reps: InterpretResult) -> InterpretResult:
    """Group reps into sets using rest-gap heuristics; emit `set` annotations."""
    raise NotImplementedError(
        "pipeline.fsm.segment_sets — implement after rep.py. Groups reps into "
        "sets via rest gaps (ROADMAP)."
    )
