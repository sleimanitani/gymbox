"""Batch replay: re-run the reference interpreter over stored sessions.

Used during algorithm tuning (architecture.md §5): pull a session's skeleton
blob, run `pipeline.rep.interpret`, and compare to the stored annotations or a
human label set. Depends on rep.py being implemented (ROADMAP Step 3).

This is a thin orchestration layer; the heavy lifting is in pipeline.rep and
the (de)serialization of the skeleton blob format.
"""

from __future__ import annotations

from ..dsl import ExerciseSpec
from .types import InterpretResult, SkeletonStream


def replay_stream(spec: ExerciseSpec, stream: SkeletonStream) -> InterpretResult:
    """Run the interpreter over an in-memory stream. (Wrapper for symmetry.)"""
    from .rep import interpret

    return interpret(spec, stream)


def decode_skeleton_blob(data: bytes) -> SkeletonStream:
    """Decode the `gymbox-v1-skeleton` compressed blob into a SkeletonStream.

    ROADMAP: implement alongside the SDK's encoder so the wire format round-trips
    (the SDK compresses via run-length on stationary frames — §4). For fixtures,
    the test harness builds SkeletonStream directly from JSON instead.
    """
    raise NotImplementedError(
        "replay.decode_skeleton_blob — implement to mirror the SDK skeleton "
        "encoder (gymbox-v1-skeleton). Tests build streams from JSON directly."
    )
