"""HTTP request/response schemas (the JSON shapes of the API).

These mirror the proto upload envelope (gymbox-proto/proto/gymbox.proto) but are
Pydantic models so FastAPI can validate/serialize them directly. In MVP-α the
body of POST /sessions is JSON described here; the skeleton blob is a separate
multipart part (architecture.md §8).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceInfoIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str
    ios_version: str
    sdk_version: str


class SessionMetaIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_session_id: str
    user_id: str
    started_at_utc: str
    ended_at_utc: str
    device: DeviceInfoIn
    exercise_id: str
    weight_kg: float | None = None


class AnnotationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_annotation_id: str
    layer_id: str
    start_s: float
    end_s: float
    value: str
    source: Literal["inference", "user", "replay"] = "inference"
    confidence: float | None = None
    metadata: dict | None = None


class UserCorrectionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # Binds to a stable client_annotation_id, never a positional index.
    client_annotation_id: str
    layer_id: str
    action: Literal["delete", "edit", "add"]
    reason: str | None = None


class SkeletonBlobRefIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    format: str = "gymbox-v1-skeleton"
    # Name of the multipart part carrying the compressed blob.
    url: str = Field(..., description="multipart part name")


class SessionUploadIn(BaseModel):
    """Body of POST /sessions (the JSON part)."""

    model_config = ConfigDict(extra="ignore")
    session: SessionMetaIn
    annotations: list[AnnotationIn] = Field(default_factory=list)
    user_corrections: list[UserCorrectionIn] = Field(default_factory=list)
    skeleton_blob: SkeletonBlobRefIn | None = None


# -- responses --------------------------------------------------------------


class UploadResult(BaseModel):
    session_id: str
    client_session_id: str
    created: bool  # True if a new session, False if an update to an existing one
    annotation_count: int


class RepOut(BaseModel):
    index_in_set: int
    start_s: float
    end_s: float
    amplitude: float | None = None
    phase_durations_s: dict | None = None


class SetOut(BaseModel):
    index_in_session: int
    start_s: float
    end_s: float
    rep_count: int
    movement_side: str | None = None
    weight_kg: float | None = None
    reps: list[RepOut] = Field(default_factory=list)


class SessionOut(BaseModel):
    id: str
    client_session_id: str
    exercise_id: str
    started_at: str
    ended_at: str
    weight_kg: float | None = None
    materialized: bool
    sets: list[SetOut] = Field(default_factory=list)


class ExerciseListItem(BaseModel):
    id: str
    display_name: str
    schema_version: int
    etag: str
