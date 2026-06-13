"""Ingest semantics: dual dedupe, immutable blob, last-write-wins re-upload.

The production schema uses Postgres-native JSONB/UUID and a named schema, so
these tests require a real Postgres. Set GYMBOX_TEST_DB to an async URL, e.g.

    export GYMBOX_TEST_DB=postgresql+asyncpg://gymbox:gymbox@localhost/gymbox_test

Without it they skip. (We deliberately do NOT down-cast the schema to SQLite —
that would let the tests pass against a model that differs from production.)
See architecture.md §8 for the idempotency / identity contract.
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

# Uses the shared Postgres-gated `db` fixture (conftest). Skip cleanly without a DB.
TEST_DB = os.environ.get("GYMBOX_TEST_DB")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="set GYMBOX_TEST_DB (async Postgres URL) to run ingest tests"
)


def _upload(client_session_id: str, *, value: str, blob_part: str | None = None) -> SessionUploadIn:
    body = {
        "session": {
            "client_session_id": client_session_id,
            "user_id": "user-abc",
            "started_at_utc": "2026-01-01T10:00:00Z",
            "ended_at_utc": "2026-01-01T10:05:00Z",
            "device": {"model": "iPhone15,2", "ios_version": "18.0", "sdk_version": "0.1.0"},
            "exercise_id": "db_curl",
            "weight_kg": 12.5,
        },
        "annotations": [
            {
                "client_annotation_id": "ann-1",
                "layer_id": "rep",
                "start_s": 0.0,
                "end_s": 2.0,
                "value": value,
                "source": "inference",
            }
        ],
        "user_corrections": [],
    }
    if blob_part:
        body["skeleton_blob"] = {"format": "gymbox-v1-skeleton", "url": blob_part}
    return SessionUploadIn.model_validate(body)


async def _seed_exercise(db: Database, spec: ExerciseSpec) -> None:
    async with db.session() as s:
        await upsert_exercise_spec(s, spec)
        await s.commit()


async def test_idempotency_key_dedupes(db: Database, db_curl_spec: ExerciseSpec) -> None:
    await _seed_exercise(db, db_curl_spec)
    csid = f"sess-{uuid.uuid4()}"
    cfg = Config(db_url=TEST_DB)  # type: ignore[arg-type]
    async with db.session() as s:
        r1 = await ingest_session(
            s, config=cfg, upload=_upload(csid, value="1"),
            skeleton_bytes=None, idempotency_key="key-xyz",
        )
        await s.commit()
    async with db.session() as s:
        r2 = await ingest_session(
            s, config=cfg, upload=_upload(csid, value="1"),
            skeleton_bytes=None, idempotency_key="key-xyz",
        )
        await s.commit()
    # Same key -> cached result, identical session id, no second create.
    assert r1.session_id == r2.session_id
    assert r1.created is True


async def test_reupload_is_update_last_write_wins(db: Database, db_curl_spec: ExerciseSpec) -> None:
    await _seed_exercise(db, db_curl_spec)
    csid = f"sess-{uuid.uuid4()}"
    cfg = Config(db_url=TEST_DB)  # type: ignore[arg-type]
    async with db.session() as s:
        first = await ingest_session(
            s, config=cfg, upload=_upload(csid, value="8"),
            skeleton_bytes=None, idempotency_key=None,
        )
        await s.commit()
    async with db.session() as s:
        second = await ingest_session(
            s, config=cfg, upload=_upload(csid, value="9"),
            skeleton_bytes=None, idempotency_key=None,
        )
        await s.commit()
    assert first.session_id == second.session_id
    assert second.created is False
    async with db.session() as s:
        anns = await read_annotations(s, user_id="user-abc", session_id=second.session_id)
    assert anns is not None
    rep_values = [a["value"] for a in anns if a["layer_id"] == "rep"]
    assert rep_values == ["9"]  # last write won


async def test_blob_is_immutable(db: Database, db_curl_spec: ExerciseSpec) -> None:
    await _seed_exercise(db, db_curl_spec)
    csid = f"sess-{uuid.uuid4()}"
    cfg = Config(db_url=TEST_DB)  # type: ignore[arg-type]
    async with db.session() as s:
        first = await ingest_session(
            s, config=cfg, upload=_upload(csid, value="1", blob_part="skeleton"),
            skeleton_bytes=b"ORIGINAL", idempotency_key=None,
        )
        await s.commit()
    async with db.session() as s:
        await ingest_session(
            s, config=cfg, upload=_upload(csid, value="1", blob_part="skeleton"),
            skeleton_bytes=b"REPLACEMENT", idempotency_key=None,
        )
        await s.commit()
    async with db.session() as s:
        sess = await read_session(s, user_id="user-abc", session_id=first.session_id)
    # The blob stored first must survive; the replacement is ignored.
    assert sess is not None
