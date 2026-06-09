"""Active/Inactive + inactive-type reference detection (architecture.md §5).

ROADMAP: later step (after rep.py / Gate A). Reference + batch-replay role, not
on the runtime critical path. Derives the `active` / `inactive` / `inactive_type`
annotation layers from the skeleton stream (movement energy + idle gaps).
"""

from __future__ import annotations

from .types import InterpretResult, SkeletonStream


def detect_activity(stream: SkeletonStream) -> InterpretResult:
    """Segment a stream into active/inactive spans and classify inactive type.

    inactive_type vocabulary: idle | setup | rest (see ANNOTATION_LAYERS).
    """
    raise NotImplementedError(
        "pipeline.activity.detect_activity — implement after Gate A. "
        "Derives active/inactive/inactive_type layers (ROADMAP)."
    )
