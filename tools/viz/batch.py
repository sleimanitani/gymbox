"""Batch reel — render every fixture into one normalized, title-carded mp4.

A marketing sizzle reel: each labelled clip is annotated (skeleton + reps/phases
via the gymbox library) and concatenated onto a common canvas with a short title
card between clips. Per-clip mp4s are still available via visualize.py.

    server/.venv/bin/python tools/viz/batch.py \
        --fixtures data/fixtures \
        --videos   training_data/Biceps_curls \
        --out      data/viz/reel.mp4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from visualize import arm_visible, interpret_arm, iter_annotated_frames  # noqa: E402

from gymbox.dsl import load_spec  # noqa: E402


def _centered(img, text, y, scale, color=(255, 255, 255), thick=2):
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x = (img.shape[1] - tw) // 2
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def title_card(cw, ch, exercise, clip, lreps, rreps, rate, secs=1.2):
    """lreps/rreps are ints, or None for an occluded arm."""
    img = np.full((ch, cw, 3), 24, np.uint8)
    cv2.rectangle(img, (0, 0), (cw, ch), (60, 60, 60), 4)
    _centered(img, "gymbox", int(ch * 0.30), 1.4, (90, 200, 250))
    _centered(img, exercise, int(ch * 0.46), 1.0)
    _centered(img, clip, int(ch * 0.56), 0.8, (210, 210, 210))
    lt = f"L {lreps}" if lreps is not None else "L occluded"
    rt = f"R {rreps}" if rreps is not None else "R occluded"
    _centered(img, f"{lt}   -   {rt}", int(ch * 0.66), 0.85, (80, 220, 80))
    return [img] * max(1, int(secs * rate))


def _match_video(fixture_stem: str, videos: Path) -> Path | None:
    name = fixture_stem.replace("_", " ")
    for ext in ("*.mp4", "*.mov", "*.avi"):
        for v in videos.glob(ext):
            if v.stem == name:
                return v
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--videos", type=Path, default=None)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[2] / "server" / "exercises" / "db_curl.json")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--canvas", default="540x960", help="WxH (portrait clips)")
    args = ap.parse_args()

    cw, ch = (int(x) for x in args.canvas.lower().split("x"))
    spec = load_spec(args.spec)
    fixtures = sorted(args.fixtures.glob("*.json"))
    if not fixtures:
        print(f"no fixtures in {args.fixtures}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rate = json.loads(fixtures[0].read_text())["sample_rate_hz"]
    writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"), rate, (cw, ch))

    total_frames = 0
    for fx in fixtures:
        fixture = json.loads(fx.read_text())
        video = _match_video(fx.stem, args.videos) if args.videos else None
        frames = fixture["frames"]
        lreps = len(interpret_arm(fixture, spec, "left_wrist")[1]) if arm_visible(frames, "left") else None
        rreps = len(interpret_arm(fixture, spec, "right_wrist")[1]) if arm_visible(frames, "right") else None
        for card in title_card(cw, ch, spec.display_name, fx.stem.replace("_", " "),
                               lreps, rreps, rate):
            writer.write(card); total_frames += 1
        for _i, img, _info in iter_annotated_frames(fixture, spec, video, canvas=(cw, ch)):
            writer.write(img); total_frames += 1
        print(f"  + {fx.stem:18s} L {lreps if lreps is not None else 'occ'} / "
              f"R {rreps if rreps is not None else 'occ'}  (video={'yes' if video else 'no'})")
    writer.release()
    print(f"\nreel -> {args.out}  ({len(fixtures)} clips, {total_frames} frames @ {rate}Hz, "
          f"{total_frames/rate:.0f}s, {cw}x{ch})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
