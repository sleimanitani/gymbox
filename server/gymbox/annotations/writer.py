"""Annotation bulk-insert helpers (architecture.md §5: gymbox.annotations.writer).

A thin, reusable layer over inserting uploaded annotations into the polymorphic
`annotations` table. The session-upload path in `api.sessions` uses this for the
common case; batch tooling (labeling, replay) reuses it too.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..persistence import Annotation


async def bulk_insert_annotations(
    session: AsyncSession,
    *,
    session_id,
    annotations: list[dict],
) -> int:
    """Insert annotation dicts for a session. Returns the number inserted.

    Each dict must carry: client_annotation_id, layer_id, start_s, end_s, value,
    source. Optional: confidence, metadata.
    """
    rows = [
        Annotation(
            client_annotation_id=a["client_annotation_id"],
            session_id=session_id,
            layer_id=a["layer_id"],
            start_s=a["start_s"],
            end_s=a["end_s"],
            value=a["value"],
            source=a.get("source", "inference"),
            confidence=a.get("confidence"),
            annotation_metadata=a.get("metadata"),
        )
        for a in annotations
    ]
    session.add_all(rows)
    await session.flush()
    return len(rows)
