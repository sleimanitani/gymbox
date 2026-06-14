"""gymbox visualizer — annotate skeletons with reps/phases (marketing tool).

Calls the gymbox library (`gymbox.pipeline.rep.interpret`) — it does NOT modify
or reimplement any detection. Given a fixture (skeleton stream + per-frame times,
as produced by server/scripts/build_fixtures.py) it:

  - runs the interpreter PER movement-side span (active wrist), since db_curl is
    single-arm and the videos alternate arms;
  - merges results into a global timeline (per-frame phase + rep boundaries);
  - renders each frame: skeleton overlay (active arm tinted by phase), a HUD
    (exercise, rep counter, phase, running TUT), rep/exercise begin-end markers,
    and a bottom timeline strip; writes an annotated mp4.

Optionally draws on the original video as background (--video); otherwise renders
on a dark canvas (works from the fixture alone). `--png-frame N` dumps a single
annotated frame to a PNG for inspection.

    server/.venv/bin/python tools/viz/visualize.py \
        --fixture data/fixtures/Bicep_Curl_5.json \
        --video   "training_data/Biceps_curls/Bicep Curl 5.mp4" \
        --out      data/viz/bicep_curl_5.mp4
    # single frame for inspection:
    ... --png-frame 120 --out data/viz/frame.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from skeleton import draw_hud, draw_skeleton, draw_timeline  # noqa: E402

# library imports — we USE gymbox, we don't change it
from gymbox.dsl import load_spec  # noqa: E402
from gymbox.pipeline.rep import interpret  # noqa: E402
from gymbox.pipeline.types import Frame, SkeletonStream  # noqa: E402

CANVAS = (1280, 720)  # (w, h) when no background video


def _side_at(t, sides):
    for s in sides:
        if s["start"] <= t < s["end"]:
            return s["value"]
    return None


def _spans(frames, sides, min_span=15):
    cur, start = None, 0
    for i, f in enumerate(frames):
        sd = _side_at(f["t_s"], sides)
        if sd != cur:
            if cur in ("Left", "Right", "Both") and i - start >= min_span:
                yield cur, start, i
            cur, start = sd, i
    if cur in ("Left", "Right", "Both") and len(frames) - start >= min_span:
        yield cur, start, len(frames)


def _spec_for_side(spec, side):
    j = "left_wrist" if side == "Left" else "right_wrist"
    if spec.signal.joint == j:
        return spec
    return spec.model_copy(update={"signal": spec.signal.model_copy(update={"joint": j})})


def interpret_timeline(fixture: dict, spec):
    """Per-side interpretation merged into global per-frame arrays.

    Returns (frame_phases, frame_side, rep_bounds, rep_index_at) all indexed by
    the global frame number.
    """
    frames = fixture["frames"]
    n = len(frames)
    sides_meta = fixture.get("meta", {}).get("movement_sides", [])
    frame_phases = ["RESET"] * n
    frame_side: list[str | None] = [None] * n
    rep_bounds: list[tuple[int, int]] = []
    rep_index_at = [0] * n  # cumulative reps completed by this frame

    spans = list(_spans(frames, sides_meta))
    if not spans:  # no side info — treat whole thing as right-side
        spans = [("Right", 0, n)]

    for side, a, b in spans:
        sub = frames[a:b]
        stream = SkeletonStream(
            sample_rate_hz=fixture["sample_rate_hz"],
            frames=[Frame(frame_index=k, t_s=sub[k]["t_s"],
                          keypoints=[tuple(kp) for kp in sub[k]["keypoints"]])
                    for k in range(len(sub))],
        )
        res = interpret(_spec_for_side(spec, side), stream)
        for k, ph in enumerate(res.frame_phases):
            frame_phases[a + k] = ph.value
            frame_side[a + k] = side
        for r in res.reps:
            sf = a + int(round(r.start_s * fixture["sample_rate_hz"])) - int(round(sub[0]["t_s"] * fixture["sample_rate_hz"]))
            ef = a + int(round(r.end_s * fixture["sample_rate_hz"])) - int(round(sub[0]["t_s"] * fixture["sample_rate_hz"]))
            rep_bounds.append((max(a, sf), min(b - 1, ef)))

    rep_bounds.sort()
    # cumulative rep counter + running TUT need per-frame state; computed in render.
    completed = 0
    bi = 0
    for i in range(n):
        while bi < len(rep_bounds) and rep_bounds[bi][1] < i:
            completed += 1
            bi += 1
        rep_index_at[i] = completed
    return frame_phases, frame_side, rep_bounds


def render(fixture: dict, spec, video: Path | None, out: Path, png_frame: int | None):
    frames = fixture["frames"]
    n = len(frames)
    rate = fixture["sample_rate_hz"]
    exercise = spec.display_name
    frame_phases, frame_side, rep_bounds = interpret_timeline(fixture, spec)
    rep_total = len(rep_bounds)

    cap = None
    if video is not None and video.exists():
        cap = cv2.VideoCapture(str(video))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    else:
        w, h = CANVAS

    writer = None
    if png_frame is None:
        out.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), rate, (w, h))

    tut = 0.0
    dt = 1.0 / rate
    for i in range(n):
        if png_frame is not None and i != png_frame:
            # still need to advance TUT + (optionally) video for the target frame
            if frame_phases[i] != "RESET":
                tut += dt
            continue
        # background
        if cap is not None:
            cap.set(cv2.CAP_PROP_POS_MSEC, frames[i]["t_s"] * 1000.0)
            ok, bg = cap.read()
            img = bg if ok else np.full((h, w, 3), 30, np.uint8)
            img = cv2.addWeighted(img, 0.55, np.zeros_like(img), 0, 0)  # dim for contrast
        else:
            img = np.full((h, w, 3), 30, np.uint8)

        ph = frame_phases[i]
        if ph != "RESET":
            tut += dt
        rep_num = sum(1 for s, e in rep_bounds if s <= i) if rep_bounds else 0
        draw_skeleton(img, frames[i]["keypoints"], active_side=frame_side[i], phase=ph)
        draw_hud(img, exercise=exercise, rep_num=min(rep_num, rep_total),
                 rep_total=rep_total, phase=ph, tut_s=tut, side=frame_side[i])
        draw_timeline(img, frame_phases=frame_phases, rep_bounds=rep_bounds, cur_frame=i)
        # rep begin/end flash
        for s, e in rep_bounds:
            if i in (s, e):
                cv2.rectangle(img, (2, 2), (w - 2, h - 2), (60, 240, 60), 6)

        if png_frame is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out), img)
            print(f"wrote frame {i} -> {out}")
            return
        writer.write(img)

    if writer is not None:
        writer.release()
        print(f"wrote {n} frames @ {rate}Hz -> {out}  ({rep_total} reps)")
    if cap is not None:
        cap.release()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, type=Path)
    ap.add_argument("--video", type=Path, default=None)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[2] / "server" / "exercises" / "db_curl.json")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--png-frame", type=int, default=None,
                    help="dump a single annotated frame index to --out (PNG) instead of mp4")
    args = ap.parse_args()

    fixture = json.loads(args.fixture.read_text())
    spec = load_spec(args.spec)
    render(fixture, spec, args.video, args.out, args.png_frame)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
