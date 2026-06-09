"""Exercise-spec persistence helpers (architecture.md §10).

Concrete: this touches only locked schema + the locked DSL models. Upserts a
validated `ExerciseSpec` into the `exercises` table and computes a stable ETag
for the OTA cache channel.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dsl import ExerciseSpec
from ..persistence import Exercise


def compute_etag(spec: ExerciseSpec) -> str:
    """Deterministic ETag from the canonicalized spec JSON.

    Canonicalization (sorted keys, no whitespace) ensures the same spec always
    yields the same ETag so phones don't re-download unchanged specs.
    """
    canonical = json.dumps(
        spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f'"{digest[:32]}"'


def spec_to_columns(spec: ExerciseSpec) -> dict:
    """Split an ExerciseSpec into the exercises-table column values."""
    return {
        "display_name": spec.display_name,
        "schema_version": spec.schema_version,
        "signal_spec": spec.signal.model_dump(mode="json"),
        "smoothing_spec": spec.smoothing.model_dump(mode="json"),
        "rep_spec": spec.rep.model_dump(mode="json"),
        "phase_spec": spec.phase.model_dump(mode="json"),
        "model_spec": spec.model_spec.model_dump(mode="json") if spec.model_spec else None,
        "etag": compute_etag(spec),
    }


def columns_to_spec_dict(row: Exercise) -> dict:
    """Reassemble the spec JSON served by GET /exercises/{id} from a DB row."""
    return {
        "id": row.id,
        "display_name": row.display_name,
        "schema_version": row.schema_version,
        "signal": row.signal_spec,
        "smoothing": row.smoothing_spec,
        "rep": row.rep_spec,
        "phase": row.phase_spec,
        "model_spec": row.model_spec,
    }


async def upsert_exercise_spec(session: AsyncSession, spec: ExerciseSpec) -> Exercise:
    """Insert or update an exercise spec row. Returns the persisted row."""
    cols = spec_to_columns(spec)
    existing = await session.get(Exercise, spec.id)
    if existing is None:
        row = Exercise(id=spec.id, **cols)
        session.add(row)
        return row
    for k, v in cols.items():
        setattr(existing, k, v)
    return existing


async def get_exercise(session: AsyncSession, exercise_id: str) -> Exercise | None:
    return await session.get(Exercise, exercise_id)


async def list_exercises(session: AsyncSession) -> list[Exercise]:
    result = await session.execute(select(Exercise).order_by(Exercise.id))
    return list(result.scalars().all())
