"""ETag + column-mapping unit tests for the OTA exercise channel (no DB).

The ETag must be deterministic so phones don't re-download unchanged specs
(architecture.md §11). spec_to_columns / columns_to_spec round-trip guards that
storing then serving a spec is lossless.
"""
from __future__ import annotations

from gymbox.api.exercises import compute_etag, spec_to_columns
from gymbox.dsl import load_spec_dict
from gymbox.dsl.models import ExerciseSpec


def test_etag_is_deterministic(db_curl_spec: ExerciseSpec) -> None:
    assert compute_etag(db_curl_spec) == compute_etag(db_curl_spec)


def test_etag_changes_with_spec(db_curl_spec: ExerciseSpec) -> None:
    mutated = db_curl_spec.model_copy(deep=True)
    mutated.smoothing.window_frames = 9  # 7 -> 9
    assert compute_etag(mutated) != compute_etag(db_curl_spec)


def test_etag_quoted(db_curl_spec: ExerciseSpec) -> None:
    et = compute_etag(db_curl_spec)
    assert et.startswith('"') and et.endswith('"')


def test_columns_round_trip(db_curl_spec: ExerciseSpec) -> None:
    cols = spec_to_columns(db_curl_spec)
    rebuilt = load_spec_dict(
        {
            "id": db_curl_spec.id,
            "display_name": cols["display_name"],
            "schema_version": cols["schema_version"],
            "signal": cols["signal_spec"],
            "smoothing": cols["smoothing_spec"],
            "rep": cols["rep_spec"],
            "phase": cols["phase_spec"],
            "model_spec": cols["model_spec"],
        }
    )
    assert compute_etag(rebuilt) == compute_etag(db_curl_spec)
