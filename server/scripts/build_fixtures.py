"""Build Gate-A fixtures from hand-labelled videos (dev-machine data prep).

For each `<video>.mp4` + matching `<video>_*.json` hand-label file, this:
  1. extracts a 33-keypoint MediaPipe Pose skeleton per frame, resampled to a
     target rate (default 15 Hz, db_curl's design rate), normalized [0,1];
  2. converts the `l11` Rep-Phase time-segments into a per-frame phase array
     (frames outside any segment -> RESET, the spec default);
  3. derives the ground-truth rep count from the number of CON (concentric)
     phase segments — the `l10` Rep layer is under-labelled in this dataset, so
     CON-count is the reliable signal (the l10 count is kept in `meta`).

Output is the Gate-A fixture schema (tests/fixtures/bicep_curl_1.json shape) plus
a `meta` block, written to the output dir (gitignored `data/` by default).

This is offline dev-machine tooling, NOT a runtime component (architecture.md
§ offline spec fitting). Run with the mediapipe extraction env:

    /tmp/poseenv/bin/python server/scripts/build_fixtures.py \
        --videos training_data/Biceps_curls \
        --labels training_data/Biceps_curls/Json_files \
        --model  /tmp/mpmodels/pose_landmarker_lite.task \
        --out    data/fixtures --hz 15
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Phase values the gymbox DSL recognises (architecture.md §10). Anything else in
# the labels (blank strings, typos) is treated as the default RESET.
VALID_PHASES = {"RESET", "CON", "ECC", "ISO_LOADED", "ISO_UNLOADED"}
REP_PHASE_LAYER = "l11"
REP_LAYER = "l10"
SIDE_LAYER = "l5"


def _match_label(video: Path, label_dir: Path) -> Path | None:
    """Find the label json whose name starts with the video stem + '_'."""
    stem = video.stem
    for j in sorted(label_dir.glob("*.json")):
        if j.stem.startswith(stem + "_") or j.stem == stem:
            return j
    return None


def _phase_at(t: float, phase_segs: list[dict]) -> str:
    """Phase label covering time t, or RESET if none (segments are [start,end))."""
    for s in phase_segs:
        if s["start"] <= t < s["end"]:
            v = s["value"]
            return v if v in VALID_PHASES else "RESET"
    return "RESET"


def extract_skeleton(video: Path, model: Path, hz: float):
    """Return (sample_rate_hz, frames[]) by resampling the video to `hz` and
    running MediaPipe Pose Lite. Frames with no detection repeat the last pose
    (rare; keeps the stream contiguous)."""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    opts = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
    )
    landmarker = vision.PoseLandmarker.create_from_options(opts)

    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = src_n / src_fps
    dt = 1.0 / hz

    frames: list[dict] = []
    last_kps: list[list[float]] | None = None
    out_i = 0
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = landmarker.detect_for_video(img, int(t * 1000.0))
        if res.pose_landmarks:
            L = res.pose_landmarks[0]
            kps = [[round(p.x, 6), round(p.y, 6), round(p.visibility, 4)] for p in L]
            last_kps = kps
        elif last_kps is not None:
            kps = last_kps
        else:
            kps = [[0.0, 0.0, 0.0] for _ in range(33)]
        frames.append({"frame_index": out_i, "t_s": round(t, 6), "keypoints": kps})
        out_i += 1
        t += dt
    cap.release()
    try:
        landmarker.close()
    except Exception:
        pass
    return src_fps, duration, frames


def build_one(video: Path, label: Path, model: Path, hz: float) -> dict:
    data = json.loads(label.read_text())
    segs = data.get("segments", [])
    phase_segs = [s for s in segs if s.get("layerId") == REP_PHASE_LAYER]
    rep_segs = [s for s in segs if s.get("layerId") == REP_LAYER]
    side_segs = [
        {"start": s["start"], "end": s["end"], "value": s["value"]}
        for s in segs
        if s.get("layerId") == SIDE_LAYER
    ]
    con_count = sum(1 for s in phase_segs if s.get("value") == "CON")

    src_fps, duration, frames = extract_skeleton(video, model, hz)
    frame_phases = [_phase_at(f["t_s"], phase_segs) for f in frames]

    return {
        "name": video.stem,
        "sample_rate_hz": hz,
        "frames": frames,
        "labels": {
            # CON-count is the reliable rep ground truth for this dataset.
            "rep_count": con_count,
            "frame_phases": frame_phases,
        },
        "meta": {
            "source_video": video.name,
            "source_label": label.name,
            "source_fps": src_fps,
            "duration_s": round(duration, 3),
            "rep_count_con": con_count,
            "rep_count_l10": len(rep_segs),
            "movement_sides": side_segs,
            "n_phase_segments": len(phase_segs),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, type=Path)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--hz", type=float, default=15.0)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    videos = sorted(
        p for ext in ("*.mp4", "*.mov", "*.avi") for p in args.videos.glob(ext)
    )
    if not videos:
        print(f"no videos under {args.videos}", file=sys.stderr)
        return 1

    for v in videos:
        label = _match_label(v, args.labels)
        if label is None:
            print(f"SKIP {v.name}: no matching label json")
            continue
        fx = build_one(v, label, args.model, args.hz)
        out = args.out / f"{v.stem.replace(' ', '_')}.json"
        out.write_text(json.dumps(fx))
        m = fx["meta"]
        print(
            f"OK {v.name:22s} -> {out.name:24s} "
            f"frames={len(fx['frames']):>4} reps(CON)={m['rep_count_con']:>2} "
            f"reps(l10)={m['rep_count_l10']:>2} sides={sorted({s['value'] for s in m['movement_sides']})}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
