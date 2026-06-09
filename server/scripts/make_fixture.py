"""Synthetic skeleton generator for the bicep_curl_1 fixture.

Produces a physically plausible dumbbell-curl skeleton stream PLUS ground-truth
labels (rep count + per-frame phase) so Gate A (architecture.md §10) is runnable
before any real labelled capture exists.

This is a STAND-IN fixture. When a real human-labelled capture lands, drop it in
at tests/fixtures/bicep_curl_1.json (same schema) and delete the synthetic one;
the synthetic generator stays for regenerating/extending coverage.

Schema of the emitted JSON (consumed by tests/conftest helpers):
{
  "name": "bicep_curl_1",
  "sample_rate_hz": 15.0,
  "frames": [{"frame_index": int, "t_s": float,
              "keypoints": [[x, y, vis], ... 33]}, ...],
  "labels": {
    "rep_count": int,
    "frame_phases": ["RESET"|"CON"|"ECC"|"ISO_LOADED"|"ISO_UNLOADED", ...]  # len == frames
  }
}

Run:
    python -m scripts.make_fixture            # writes tests/fixtures/bicep_curl_1.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# MediaPipe Pose has 33 keypoints; we animate only the right arm joints used by
# db_curl and keep the rest at fixed, plausible positions.
NUM_KEYPOINTS = 33

# Indices (must match dsl/keypoints.py).
RIGHT_SHOULDER = 12
RIGHT_ELBOW = 14
RIGHT_WRIST = 16


def _base_pose() -> list[list[float]]:
    """A static, plausible standing pose (normalized coords). y grows downward."""
    pose = [[0.5, 0.5, 0.9] for _ in range(NUM_KEYPOINTS)]
    # Rough vertical layout: head ~0.15, shoulders ~0.30, hips ~0.55, ankles ~0.95.
    pose[0] = [0.50, 0.15, 0.99]   # nose
    pose[11] = [0.44, 0.30, 0.98]  # left_shoulder
    pose[12] = [0.56, 0.30, 0.98]  # right_shoulder
    pose[13] = [0.42, 0.45, 0.97]  # left_elbow
    pose[14] = [0.58, 0.45, 0.97]  # right_elbow (animated y below)
    pose[15] = [0.41, 0.58, 0.96]  # left_wrist
    pose[16] = [0.59, 0.58, 0.96]  # right_wrist (animated y below)
    pose[23] = [0.46, 0.55, 0.97]  # left_hip
    pose[24] = [0.54, 0.55, 0.97]  # right_hip
    pose[25] = [0.46, 0.72, 0.96]  # left_knee
    pose[26] = [0.54, 0.72, 0.96]  # right_knee
    pose[27] = [0.46, 0.92, 0.95]  # left_ankle
    pose[28] = [0.54, 0.92, 0.95]  # right_ankle
    return pose


def generate(
    *,
    n_reps: int = 8,
    sample_rate_hz: float = 15.0,
    con_s: float = 0.8,        # concentric (lifting) duration
    ecc_s: float = 1.2,        # eccentric (lowering) duration
    hold_top_s: float = 0.25,  # ISO_UNLOADED hold at top
    hold_bottom_s: float = 0.4,  # ISO_LOADED hold at bottom
    lead_in_s: float = 1.0,    # RESET before first rep
    noise: float = 0.004,      # gaussian-ish jitter amplitude
    seed: int = 7,
) -> dict:
    """Generate the fixture dict.

    Wrist y oscillates between an extended (bottom, larger y) and flexed (top,
    smaller y) position. Elbow stays roughly fixed; the wrist describes the arc.
    Phase ground-truth is emitted per frame from the synthesis schedule, so it is
    exact by construction (the interpreter's job is to recover it from geometry).
    """
    import random

    rng = random.Random(seed)

    y_bottom = 0.58  # extended arm (wrist low on screen = large y)
    y_top = 0.34     # flexed arm (wrist high on screen = small y)

    frames: list[dict] = []
    phases: list[str] = []
    t = 0.0
    fi = 0
    dt = 1.0 / sample_rate_hz

    def emit(wrist_y: float, phase: str) -> None:
        nonlocal fi, t
        pose = _base_pose()
        # jitter all animated joints slightly
        wy = wrist_y + rng.uniform(-noise, noise)
        pose[RIGHT_WRIST] = [0.59 + rng.uniform(-noise, noise), wy, 0.96]
        # elbow tracks a fraction of wrist motion (arc), shoulder ~fixed
        elbow_y = 0.45 + 0.10 * (wrist_y - y_bottom) / (y_top - y_bottom)
        pose[RIGHT_ELBOW] = [0.58 + rng.uniform(-noise, noise), elbow_y, 0.97]
        frames.append(
            {
                "frame_index": fi,
                "t_s": round(t, 6),
                "keypoints": [[round(x, 6), round(y, 6), round(v, 4)] for x, y, v in pose],
            }
        )
        phases.append(phase)
        fi += 1
        t += dt

    def n_frames(seconds: float) -> int:
        return max(1, int(round(seconds * sample_rate_hz)))

    # Lead-in: RESET at the mid/bottom.
    for _ in range(n_frames(lead_in_s)):
        emit(y_bottom, "RESET")

    for _ in range(n_reps):
        # ISO_LOADED hold at bottom (arm extended).
        for _ in range(n_frames(hold_bottom_s)):
            emit(y_bottom, "ISO_LOADED")
        # CON: lift bottom -> top (y decreases).
        cf = n_frames(con_s)
        for k in range(cf):
            frac = (k + 1) / cf
            # ease-in-out for plausibility
            s = 0.5 - 0.5 * math.cos(math.pi * frac)
            emit(y_bottom + (y_top - y_bottom) * s, "CON")
        # ISO_UNLOADED hold at top (arm flexed).
        for _ in range(n_frames(hold_top_s)):
            emit(y_top, "ISO_UNLOADED")
        # ECC: lower top -> bottom (y increases).
        ef = n_frames(ecc_s)
        for k in range(ef):
            frac = (k + 1) / ef
            s = 0.5 - 0.5 * math.cos(math.pi * frac)
            emit(y_top + (y_bottom - y_top) * s, "ECC")

    # Trailing RESET.
    for _ in range(n_frames(0.6)):
        emit(y_bottom, "RESET")

    return {
        "name": "bicep_curl_1",
        "sample_rate_hz": sample_rate_hz,
        "frames": frames,
        "labels": {
            "rep_count": n_reps,
            "frame_phases": phases,
        },
    }


def write(path: str | Path, **kwargs) -> Path:
    data = generate(**kwargs)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


if __name__ == "__main__":  # pragma: no cover
    here = Path(__file__).resolve().parents[1]  # server/
    out = here / "tests" / "fixtures" / "bicep_curl_1.json"
    written = write(out)
    d = json.loads(written.read_text())
    print(f"wrote {written} — {len(d['frames'])} frames, {d['labels']['rep_count']} reps")
