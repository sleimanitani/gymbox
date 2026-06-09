"""Session ingest + read helpers (architecture.md §8).

Concrete implementations of the locked upload semantics:

  - `client_session_id` is durable identity: re-upload = update, last-write-wins
    on annotations and corrections; skeleton blob immutable once stored.
  - `Idempotency-Key` dedupes transport retries of a single upload attempt.
  - corrections bind to `client_annotation_id` (stable), resolved at insert time.

The materializer (separate module) later denormalizes annotations into
sessions/sets/reps; reads here surface whatever the materializer has produced.
"""

from __future__ import annotations

import datetime as dt
import time

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config
from ..persistence import Annotation, Camera, Session, SkeletonBlob, User
from ..persistence.blobs import make_blob_store
from .schemas import RepOut, SessionOut, SetOut, UploadResult

# In-process Idempotency-Key cache: key -> (UploadResult, expires_at_monotonic).
# Process-local by design; sufficient for a single-instance reference box. A
# multi-instance integrator deployment would back this with Redis (documented
# in §8 as a transport-level concern).
_IDEMPOTENCY_CACHE: dict[str, tuple[UploadResult, float]] = {}


def _parse_rfc3339(s: str) -> dt.datetime:
    # Accept trailing 'Z'.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return dt.datetime.fromisoformat(s)


async def _get_or_create_user(session: AsyncSession, external_user_id: str) -> User:
    result = await session.execute(
        select(User).where(User.external_user_id == external_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(external_user_id=external_user_id)
        session.add(user)
        await session.flush()
    return user


async def ingest_session(
    session: AsyncSession,
    *,
    config: Config,
    upload,  # SessionUploadIn
    skeleton_bytes: bytes | None,
    idempotency_key: str | None,
) -> UploadResult:
    """Ingest an upload. Handles both dedupe layers + upsert semantics."""
    # 1. Transport-level idempotency: same key -> return cached result.
    now = time.monotonic()
    if idempotency_key:
        cached = _IDEMPOTENCY_CACHE.get(idempotency_key)
        if cached and cached[1] > now:
            return cached[0]

    meta = upload.session
    user = await _get_or_create_user(session, meta.user_id)

    # 2. Durable session identity: upsert by client_session_id.
    result = await session.execute(
        select(Session).where(Session.client_session_id == meta.client_session_id)
    )
    existing = result.scalar_one_or_none()
    created = existing is None

    if existing is None:
        # One camera row per phone (architecture.md §9). Reuse-by-model is a
        # later refinement; MVP-α creates a row per session's device.
        camera = Camera(kind="phone", device_model=meta.device.model)
        session.add(camera)
        await session.flush()

        row = Session(
            client_session_id=meta.client_session_id,
            user_id=user.id,
            camera_id=camera.id,
            exercise_id=meta.exercise_id,
            started_at=_parse_rfc3339(meta.started_at_utc),
            ended_at=_parse_rfc3339(meta.ended_at_utc),
            weight_kg=meta.weight_kg,
            device_model=meta.device.model,
            ios_version=meta.device.ios_version,
            sdk_version=meta.device.sdk_version,
            last_idempotency_key=idempotency_key,
            materialized=False,
        )
        session.add(row)
        await session.flush()
    else:
        # Update metadata; mark for re-materialization. Blob is immutable.
        existing.exercise_id = meta.exercise_id
        existing.started_at = _parse_rfc3339(meta.started_at_utc)
        existing.ended_at = _parse_rfc3339(meta.ended_at_utc)
        existing.weight_kg = meta.weight_kg
        existing.last_idempotency_key = idempotency_key
        existing.materialized = False
        row = existing

    # 3. Annotations: last-write-wins. Replace the full annotation set, then
    #    apply corrections. Corrections bind by client_annotation_id.
    await _write_annotations(session, row, upload)

    # 4. Skeleton blob: store only if none exists for this session (immutable).
    if skeleton_bytes is not None:
        await _store_blob_if_absent(
            session, row, config, upload, skeleton_bytes
        )

    result_obj = UploadResult(
        session_id=str(row.id),
        client_session_id=row.client_session_id,
        created=created,
        annotation_count=len(upload.annotations),
    )

    if idempotency_key:
        _IDEMPOTENCY_CACHE[idempotency_key] = (
            result_obj,
            now + config.idempotency_ttl_s,
        )
    return result_obj


async def _write_annotations(session: AsyncSession, row: Session, upload) -> None:
    """Replace the session's annotations (last-write-wins) and apply corrections."""
    # Clear existing annotations for this session.
    await session.execute(
        delete(Annotation).where(Annotation.session_id == row.id)
    )

    # Build a map so corrections can be applied before insert.
    by_id = {a.client_annotation_id: a for a in upload.annotations}

    # Apply corrections (architecture.md §8): delete/edit/add by stable id.
    for corr in upload.user_corrections:
        if corr.action == "delete":
            by_id.pop(corr.client_annotation_id, None)
        elif corr.action == "edit":
            # An edit is expected to also appear in `annotations` with the new
            # value; we keep whatever is in `annotations` as source of truth and
            # just record provenance below. No-op here beyond ensuring presence.
            pass
        elif corr.action == "add":
            # The added annotation appears in `annotations` already; nothing to do.
            pass

    for ann in by_id.values():
        # Mark corrected annotations' source as "user" if a correction targeted them.
        corrected = any(
            c.client_annotation_id == ann.client_annotation_id
            and c.action in ("edit", "add")
            for c in upload.user_corrections
        )
        session.add(
            Annotation(
                client_annotation_id=ann.client_annotation_id,
                session_id=row.id,
                layer_id=ann.layer_id,
                start_s=ann.start_s,
                end_s=ann.end_s,
                value=ann.value,
                source="user" if corrected else ann.source,
                confidence=ann.confidence,
                annotation_metadata=ann.metadata,
            )
        )
    await session.flush()


async def _store_blob_if_absent(
    session: AsyncSession, row: Session, config: Config, upload, data: bytes
) -> None:
    existing = await session.execute(
        select(SkeletonBlob).where(SkeletonBlob.session_id == row.id)
    )
    if existing.scalar_one_or_none() is not None:
        return  # immutable — do not replace

    store = make_blob_store(config.blob_storage_url)
    fmt = upload.skeleton_blob.format if upload.skeleton_blob else "gymbox-v1-skeleton"
    storage_url, sha, size = await store.put(str(row.id), data)
    session.add(
        SkeletonBlob(
            session_id=row.id,
            format=fmt,
            storage_url=storage_url,
            sha256=sha,
            byte_size=size,
            data=None,  # stored externally; not inlined
        )
    )
    await session.flush()


# -- reads ------------------------------------------------------------------


async def _owned_session(
    session: AsyncSession, session_id: str, user_id: str
) -> Session | None:
    """Fetch a session by id, scoped to the authenticated user (ownership check)."""
    try:
        import uuid

        sid = uuid.UUID(session_id)
    except ValueError:
        return None
    row = await session.get(Session, sid)
    if row is None:
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.external_user_id != user_id:
        return None
    return row


async def read_session(
    session: AsyncSession, *, session_id: str, user_id: str
) -> SessionOut | None:
    row = await _owned_session(session, session_id, user_id)
    if row is None:
        return None

    # Load materialized sets + reps.
    from ..persistence import Rep, Set

    sets_res = await session.execute(
        select(Set).where(Set.session_id == row.id).order_by(Set.index_in_session)
    )
    sets = list(sets_res.scalars().all())
    reps_res = await session.execute(
        select(Rep).where(Rep.session_id == row.id).order_by(Rep.index_in_set)
    )
    reps = list(reps_res.scalars().all())
    reps_by_set: dict = {}
    for r in reps:
        reps_by_set.setdefault(r.set_id, []).append(r)

    set_outs = []
    for s in sets:
        set_outs.append(
            SetOut(
                index_in_session=s.index_in_session,
                start_s=s.start_s,
                end_s=s.end_s,
                rep_count=s.rep_count,
                movement_side=s.movement_side,
                weight_kg=s.weight_kg,
                reps=[
                    RepOut(
                        index_in_set=r.index_in_set,
                        start_s=r.start_s,
                        end_s=r.end_s,
                        amplitude=r.amplitude,
                        phase_durations_s=r.phase_durations_s,
                    )
                    for r in reps_by_set.get(s.id, [])
                ],
            )
        )

    return SessionOut(
        id=str(row.id),
        client_session_id=row.client_session_id,
        exercise_id=row.exercise_id,
        started_at=row.started_at.isoformat(),
        ended_at=row.ended_at.isoformat(),
        weight_kg=row.weight_kg,
        materialized=row.materialized,
        sets=set_outs,
    )


async def list_user_sessions(
    session: AsyncSession, *, user_id: str, limit: int, offset: int
) -> list[SessionOut]:
    user_res = await session.execute(
        select(User).where(User.external_user_id == user_id)
    )
    user = user_res.scalar_one_or_none()
    if user is None:
        return []
    res = await session.execute(
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(res.scalars().all())
    return [
        SessionOut(
            id=str(r.id),
            client_session_id=r.client_session_id,
            exercise_id=r.exercise_id,
            started_at=r.started_at.isoformat(),
            ended_at=r.ended_at.isoformat(),
            weight_kg=r.weight_kg,
            materialized=r.materialized,
            sets=[],
        )
        for r in rows
    ]


async def read_annotations(
    session: AsyncSession, *, session_id: str, user_id: str
) -> list[dict] | None:
    row = await _owned_session(session, session_id, user_id)
    if row is None:
        return None
    res = await session.execute(
        select(Annotation)
        .where(Annotation.session_id == row.id)
        .order_by(Annotation.start_s)
    )
    return [
        {
            "client_annotation_id": a.client_annotation_id,
            "layer_id": a.layer_id,
            "start_s": a.start_s,
            "end_s": a.end_s,
            "value": a.value,
            "source": a.source,
            "confidence": a.confidence,
            "metadata": a.annotation_metadata,
        }
        for a in res.scalars().all()
    ]
