"""Step 9 — end-to-end integration round-trip (the "MVP-α done" bar).

Exercises the full edge→server path against real Postgres:

    interpreter detects reps/phases  (Python oracle == the phone's Swift port,
                                       proven by Gate B)
        → build the upload envelope   (rep + rep_phase annotations, exactly what
                                       SessionRecorder.reinterpret + Uploader send)
        → ingest_session              (the real /sessions ingest path)
        → materialize                 (annotations → sets/reps)
        → read_session                (query API returns materialized sets/reps)

Acceptance (ROADMAP Step 9): a real session round-trips into Postgres and reads
back out with all 8 reps materialized, each carrying phase durations.

Postgres-gated (GYMBOX_TEST_DB); uses the shared `db` fixture from conftest. The
persistence layer is Postgres-only by design — no SQLite down-cast (CLAUDE.md).
"""
from __future__ import annotations

import os
import uuid

import pytest

from gymbox.api.exercises import upsert_exercise_spec
from gymbox.api.schemas import SessionUploadIn
from gymbox.api.sessions import ingest_session, read_annotations, read_session
from gymbox.config import Config
from gymbox.dsl.models import ExerciseSpec
from gymbox.materializer import materialize_pending
from gymbox.pipeline.rep import interpret
from gymbox.pipeline.types import SkeletonStream

TEST_DB = os.environ.get("GYMBOX_TEST_DB")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="set GYMBOX_TEST_DB (async Postgres URL) to run integration test"
)

USER = "user-integration"


def _build_upload(csid: str, result, *, weight_kg: float) -> SessionUploadIn:
    """Build the upload envelope from an InterpretResult — mirrors what the phone
    sends (SessionRecorder.reinterpret annotations + Uploader.encodeBody)."""
    annotations = [
        {
            "client_annotation_id": f"{csid}:rep:{r.index}",
            "layer_id": "rep",
            "start_s": r.start_s,
            "end_s": r.end_s,
            "value": str(r.index + 1),
            "source": "inference",
        }
        for r in result.reps
    ] + [
        {
            "client_annotation_id": f"{csid}:rep_phase:{i}",
            "layer_id": "rep_phase",
            "start_s": seg.start_s,
            "end_s": seg.end_s,
            "value": seg.label.value,
            "source": "inference",
        }
        for i, seg in enumerate(result.phase_segments)
    ]
    return SessionUploadIn.model_validate(
        {
            "session": {
                "client_session_id": csid,
                "user_id": USER,
                "started_at_utc": "2026-01-01T10:00:00Z",
                "ended_at_utc": "2026-01-01T10:00:23Z",
                "device": {"model": "iPhone15,2", "ios_version": "18.0", "sdk_version": "0.1.0"},
                "exercise_id": "db_curl",
                "weight_kg": weight_kg,
            },
            "annotations": annotations,
            "user_corrections": [],
            "skeleton_blob": {"format": "gymbox-v1-skeleton", "url": "skeleton"},
        }
    )


async def test_session_roundtrips_into_postgres_and_back(
    db, db_curl_spec: ExerciseSpec, bicep_stream: SkeletonStream
) -> None:
    # 0. Detect (the same interpreter the phone runs; Gate B proves parity).
    result = interpret(db_curl_spec, bicep_stream)
    assert result.rep_count == 8

    # Seed the exercise spec the session references.
    async with db.session() as s:
        await upsert_exercise_spec(s, db_curl_spec)
        await s.commit()

    csid = f"sess-{uuid.uuid4()}"
    cfg = Config(db_url=TEST_DB)  # type: ignore[arg-type]

    # 1. Upload through the real ingest path (with a skeleton blob).
    async with db.session() as s:
        up = await ingest_session(
            s, config=cfg, upload=_build_upload(csid, result, weight_kg=12.5),
            skeleton_bytes=b"SKELETON-BLOB-BYTES", idempotency_key="idem-1",
        )
        await s.commit()
    assert up.created is True
    db_session_id = up.session_id

    # 2. Materialize annotations → sets/reps (the background job, run inline).
    async with db.session() as s:
        n = await materialize_pending(s)
        await s.commit()
    assert n >= 1

    # 3. Read back the materialized session via the query API.
    async with db.session() as s:
        out = await read_session(s, user_id=USER, session_id=db_session_id)
    assert out is not None
    assert out.materialized is True
    assert out.exercise_id == "db_curl"
    assert out.weight_kg == 12.5

    # A single set spanning the session (synthesized when no explicit set layer),
    # with all 8 reps assigned to it.
    assert len(out.sets) == 1
    the_set = out.sets[0]
    assert the_set.rep_count == 8
    assert len(the_set.reps) == 8

    # Every rep carries phase durations summed from the rep_phase track, and the
    # phases are drawn from the locked vocabulary.
    allowed = {"CON", "ECC", "ISO_LOADED", "ISO_UNLOADED", "RESET"}
    for rep in the_set.reps:
        assert rep.phase_durations_s, f"rep {rep.index_in_set} has no phase durations"
        assert set(rep.phase_durations_s).issubset(allowed)
        assert rep.end_s > rep.start_s

    # Reps are time-ordered.
    starts = [r.start_s for r in the_set.reps]
    assert starts == sorted(starts)


async def test_annotations_roundtrip_verbatim(
    db, db_curl_spec: ExerciseSpec, bicep_stream: SkeletonStream
) -> None:
    """The stored annotations match what was uploaded (rep + rep_phase counts)."""
    result = interpret(db_curl_spec, bicep_stream)
    async with db.session() as s:
        await upsert_exercise_spec(s, db_curl_spec)
        await s.commit()

    csid = f"sess-{uuid.uuid4()}"
    cfg = Config(db_url=TEST_DB)  # type: ignore[arg-type]
    async with db.session() as s:
        up = await ingest_session(
            s, config=cfg, upload=_build_upload(csid, result, weight_kg=10.0),
            skeleton_bytes=None, idempotency_key=None,
        )
        await s.commit()

    async with db.session() as s:
        anns = await read_annotations(s, user_id=USER, session_id=up.session_id)
    assert anns is not None
    rep_rows = [a for a in anns if a["layer_id"] == "rep"]
    phase_rows = [a for a in anns if a["layer_id"] == "rep_phase"]
    assert len(rep_rows) == result.rep_count == 8
    assert len(phase_rows) == len(result.phase_segments)
    # rep_phase values are phase labels (what the materializer keys durations by).
    assert all(a["value"] in {"CON", "ECC", "ISO_LOADED", "ISO_UNLOADED", "RESET"} for a in phase_rows)
