"""Shared test fixtures.

Loads the human-labelled (or, until a real capture lands, synthetic) skeleton
fixture and exposes it as the typed objects the pipeline consumes, plus the
ground-truth labels the two gates score against. See architecture.md §12.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gymbox.dsl import PhaseLabel, load_spec
from gymbox.dsl.models import ExerciseSpec
from gymbox.persistence import Database
from gymbox.pipeline.types import Frame, SkeletonStream

FIXTURES = Path(__file__).parent / "fixtures"
EXERCISES = Path(__file__).parents[1] / "exercises"

# Postgres-gated DB tests share this. The persistence layer is Postgres-only by
# design (JSONB/UUID + named schema); we do NOT down-cast to SQLite (CLAUDE.md).
TEST_DB = os.environ.get("GYMBOX_TEST_DB")
requires_db = pytest.mark.skipif(
    not TEST_DB, reason="set GYMBOX_TEST_DB (async Postgres URL) to run DB tests"
)


@pytest.fixture
async def db() -> Database:
    """A ready-to-use Database against GYMBOX_TEST_DB: tables created and the
    annotation-layer FK rows seeded (so annotation inserts don't violate the
    layer FK). Mirrors what Alembic does in production."""
    database = Database(TEST_DB)  # type: ignore[arg-type]
    await database.create_all()
    await database.seed_reference_data()
    yield database
    await database.dispose()


def _load_fixture(name: str) -> dict:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        pytest.skip(
            f"fixture {path} missing — run `python scripts/make_fixture.py` "
            "to generate the synthetic stand-in, or drop in a real labelled capture"
        )
    with path.open() as fh:
        return json.load(fh)


def _stream_from_fixture(data: dict) -> SkeletonStream:
    frames = [
        Frame(
            frame_index=f["frame_index"],
            t_s=f["t_s"],
            keypoints=[tuple(kp) for kp in f["keypoints"]],
        )
        for f in data["frames"]
    ]
    return SkeletonStream(sample_rate_hz=data["sample_rate_hz"], frames=frames)


@pytest.fixture(scope="session")
def bicep_fixture() -> dict:
    return _load_fixture("bicep_curl_1")


@pytest.fixture(scope="session")
def bicep_stream(bicep_fixture: dict) -> SkeletonStream:
    return _stream_from_fixture(bicep_fixture)


@pytest.fixture(scope="session")
def bicep_truth_phases(bicep_fixture: dict) -> list[PhaseLabel]:
    return [PhaseLabel(p) for p in bicep_fixture["labels"]["frame_phases"]]


@pytest.fixture(scope="session")
def bicep_truth_rep_count(bicep_fixture: dict) -> int:
    return int(bicep_fixture["labels"]["rep_count"])


@pytest.fixture(scope="session")
def db_curl_spec() -> ExerciseSpec:
    return load_spec(EXERCISES / "db_curl.json")
