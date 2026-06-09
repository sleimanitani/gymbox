"""gymbox persistence layer.

Async SQLAlchemy engine + session factory, ORM models, and the canonical list
of the 13 annotation layers (seeded by the initial migration).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import (
    SCHEMA,
    Annotation,
    AnnotationLayer,
    Base,
    BodyEmbedding,
    Camera,
    Exercise,
    ExerciseModel,
    LabeledClip,
    Rep,
    Session,
    Set,
    SkeletonBlob,
    User,
)

__all__ = [
    "SCHEMA",
    "ANNOTATION_LAYERS",
    "Annotation",
    "AnnotationLayer",
    "Base",
    "BodyEmbedding",
    "Camera",
    "Database",
    "Exercise",
    "ExerciseModel",
    "LabeledClip",
    "Rep",
    "Session",
    "Set",
    "SkeletonBlob",
    "User",
]


# The 13 annotation layers (architecture.md §9). Seeded by migration; this is
# the source list the seed reads from.
ANNOTATION_LAYERS: list[dict] = [
    {"id": "capture", "description": "Raw capture span / recording boundaries."},
    {"id": "session", "description": "A complete workout session."},
    {"id": "exercise", "description": "Which exercise is being performed.",
     "allowed_values": None},
    {"id": "equipment", "description": "Equipment in use (dumbbell, cable, machine)."},
    {"id": "weight", "description": "Weight value for the span (kg)."},
    {"id": "movement_side", "description": "left | right | both | alternating.",
     "allowed_values": ["left", "right", "both", "alternating"]},
    {"id": "set", "description": "A set: a contiguous group of reps."},
    {"id": "active", "description": "User is actively exercising."},
    {"id": "inactive", "description": "User is not exercising."},
    {"id": "inactive_type", "description": "idle | setup | rest.",
     "allowed_values": ["idle", "setup", "rest"]},
    {"id": "rep", "description": "A single repetition."},
    {"id": "rep_phase", "description": "CON | ECC | ISO_LOADED | ISO_UNLOADED | RESET.",
     "allowed_values": ["CON", "ECC", "ISO_LOADED", "ISO_UNLOADED", "RESET"]},
    {"id": "camera_angle", "description": "front | three_quarter | side | back.",
     "allowed_values": ["front", "three_quarter", "side", "back"]},
]

assert len(ANNOTATION_LAYERS) == 13, "there are exactly 13 annotation layers"


class Database:
    """Owns the async engine and a session factory.

    Tables are created via Alembic migrations in production. `create_all()` is
    a convenience for the reference box / tests only.
    """

    def __init__(self, db_url: str, echo: bool = False) -> None:
        self._engine: AsyncEngine = create_async_engine(db_url, echo=echo, future=True)
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as s:
            yield s

    async def create_all(self) -> None:
        """Create the schema and all tables. Reference-box / test convenience.

        Production uses Alembic (`alembic upgrade head`).
        """
        from sqlalchemy.schema import CreateSchema

        async with self._engine.begin() as conn:
            await conn.execute(CreateSchema(SCHEMA, if_not_exists=True))
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()
