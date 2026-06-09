"""SQLAlchemy 2.x async ORM models (architecture.md §9).

All gymbox tables live under a schema prefix so the library is a well-behaved
tenant in the integrator's database. The 13 annotation layers are seeded by
migration (see migrations/versions). Tables marked "schema only" in §9 are
defined here but unused in MVP-α (exercise_models, labeled_clips,
body_embeddings).

The phone produces the 13 annotation layers and the server stores them; the
materializer denormalizes annotations into sessions/sets/reps asynchronously.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Schema prefix for all gymbox-owned tables.
SCHEMA = "gymbox"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    metadata = None  # set below via __init_subclass__-free explicit MetaData

    type_annotation_map = {
        dict[str, Any]: JSONB,
    }


# Bind a MetaData carrying the schema. (Done after class def to keep type
# checkers happy.)
from sqlalchemy import MetaData  # noqa: E402

Base.metadata = MetaData(schema=SCHEMA)


# ---------------------------------------------------------------------------
# Core identity / device
# ---------------------------------------------------------------------------


class User(Base):
    """Mirror of the integrator's user identities. Created on first upload.
    `token_hash` exists for the reference box's DefaultTokenValidator and for
    Phase 1+ ReID; production integrators validate tokens in their own system.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    # The integrator's user identifier (their primary key, opaque to us).
    external_user_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    # Argon2id hash; only populated by the reference DefaultTokenValidator.
    token_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Camera(Base):
    """Devices that produced data. MVP-α: one row per phone. Forward-compat for
    fixed cameras (Phase 1+)."""

    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), default="phone")  # phone | fixed
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Exercises / specs / models
# ---------------------------------------------------------------------------


class Exercise(Base):
    """DSL specs. rep_spec and phase_spec are JSONB columns (architecture.md §9, §10)."""

    __tablename__ = "exercises"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "db_curl"
    display_name: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    # The signal + smoothing portions of the spec.
    signal_spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    smoothing_spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The two JSONB columns called out explicitly in §9.
    rep_spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    phase_spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Reserved (§11.2); null in MVP-α.
    model_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Opaque cache validator served on GET /exercises/{id}.
    etag: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    models: Mapped[list["ExerciseModel"]] = relationship(back_populates="exercise")


class ExerciseModel(Base):
    """Optional per-exercise model file references (architecture.md §9, §11.2).
    Empty in MVP-α; populated when MVP-β classifier heads are trained."""

    __tablename__ = "exercise_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    exercise_id: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.exercises.id"))
    version: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_url: Mapped[str] = mapped_column(Text)
    pushed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    exercise: Mapped["Exercise"] = relationship(back_populates="models")

    __table_args__ = (UniqueConstraint("exercise_id", "version", name="uq_exercise_model_version"),)


# ---------------------------------------------------------------------------
# Sessions / materialized sets & reps
# ---------------------------------------------------------------------------


class Session(Base):
    """One row per uploaded workout session.

    `client_session_id` is the durable identity: a re-upload with the same value
    is an UPDATE (last-write-wins on annotations; skeleton blob immutable).
    `last_idempotency_key` records the most recent transport-level dedupe key.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    client_session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.users.id"), index=True)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.cameras.id"), nullable=True
    )
    exercise_id: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.exercises.id"))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ios_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sdk_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Transport-level dedupe (Idempotency-Key header) — most recent upload attempt.
    last_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Whether the materializer has processed the current annotation set.
    materialized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    annotations: Mapped[list["Annotation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    sets: Mapped[list["Set"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    reps: Mapped[list["Rep"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    skeleton_blob: Mapped["SkeletonBlob"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class Set(Base):
    """Materialized from annotations. One row per set."""

    __tablename__ = "sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.sessions.id"), index=True
    )
    index_in_session: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    rep_count: Mapped[int] = mapped_column(Integer, default=0)
    movement_side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="sets")


class Rep(Base):
    """Materialized from annotations. One row per rep."""

    __tablename__ = "reps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.sessions.id"), index=True
    )
    set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.sets.id"), nullable=True
    )
    index_in_set: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    # Peak-to-peak normalized amplitude of the tracked signal for this rep.
    amplitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Per-phase durations in seconds, e.g. {"CON": 0.7, "ECC": 1.4, ...}.
    phase_durations_s: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="reps")


# ---------------------------------------------------------------------------
# Annotation layers + polymorphic annotations
# ---------------------------------------------------------------------------


class AnnotationLayer(Base):
    """The 13 layer definitions (architecture.md §9). Seeded by migration."""

    __tablename__ = "annotation_layers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "rep_phase"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional JSON list of allowed values for closed-vocabulary layers.
    allowed_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Annotation(Base):
    """Polymorphic source of truth (architecture.md §9).

    Bound to a session_id OR a clip_id (XOR). Carries the stable
    `client_annotation_id` assigned on the phone so user_corrections resolve
    against it at insert time (never positional index).
    """

    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    # Stable id assigned on device. Unique within a session.
    client_annotation_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.sessions.id"), nullable=True, index=True
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.labeled_clips.id"), nullable=True, index=True
    )
    layer_id: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.annotation_layers.id"))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    value: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))  # inference | user | replay
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    annotation_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    session: Mapped["Session | None"] = relationship(back_populates="annotations")

    __table_args__ = (
        UniqueConstraint(
            "session_id", "client_annotation_id", name="uq_session_client_annotation_id"
        ),
        Index("ix_annotations_session_layer", "session_id", "layer_id"),
    )


# ---------------------------------------------------------------------------
# Blobs / clips / embeddings
# ---------------------------------------------------------------------------


class SkeletonBlob(Base):
    """Uploaded compressed pose streams. Stored in object storage; this row
    holds the reference + metadata. Immutable once first stored (architecture.md §8).
    For the reference box, `data` may hold bytes inline on local FS instead.
    """

    __tablename__ = "skeleton_blobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.sessions.id"), unique=True, index=True
    )
    format: Mapped[str] = mapped_column(String(32))  # "gymbox-v1-skeleton"
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Reference-box convenience: inline bytes when no object store is configured.
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped["Session"] = relationship(back_populates="skeleton_blob")


class LabeledClip(Base):
    """Human-labeled clips for offline training. Populated when labeling begins
    (schema only in MVP-α)."""

    __tablename__ = "labeled_clips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.sessions.id"), nullable=True
    )
    exercise_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    label_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BodyEmbedding(Base):
    """pgvector(512) CLIP-ReID embeddings (Phase 1+). Empty in MVP-α.

    The vector column is declared as JSON here to avoid a hard pgvector
    dependency for MVP-α; the migration that turns this into a real
    `vector(512)` + HNSW index ships with Phase 1 (architecture.md §6).
    """

    __tablename__ = "body_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id"), nullable=True, index=True
    )
    visit_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Placeholder until pgvector migration (Phase 1). JSON list of 512 floats.
    embedding: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
