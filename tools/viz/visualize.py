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
annotated frame to a PNG for inspection. `iter_annotated_frames()` is reused by
batch.py to build a multi-clip reel.

    server/.venv/bin/python tools/viz/visualize.py \
        --fixture data/fixtures/Bicep_Curl_5.json \
        --video   "training_data/Biceps_curls/Bicep Curl 5.mp4" \
        --out      data/viz/bicep_curl_5.mp4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from skeleton import (  # noqa: E402
    draw_hud,
    draw_hud_dual,
    draw_skeleton,
    draw_skeleton_dual,
    draw_timeline,
    draw_timeline_dual,
)

# library imports — we USE gymbox, we don't change it
from gymbox.dsl import load_spec  # noqa: E402
from gymbox.pipeline.rep import interpret  # noqa: E402
from gymbox.pipeline.types import Frame, SkeletonStream  # noqa: E402

CANVAS = (1280, 720)  # (w, h) when no background video and no --canvas


def letterbox(img: np.ndarray, cw: int, ch: int, pad: int = 20) -> np.ndarray:
    """Fit `img` into a (cw, ch) canvas preserving aspect, centered on dark pad."""
    h, w = img.shape[:2]
    scale = min(cw / w, ch / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((ch, cw, 3), pad, np.uint8)
    x, y = (cw - nw) // 2, (ch - nh) // 2
    canvas[y:y + nh, x:x + nw] = resized
    return canvas


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

    Returns (frame_phases, frame_side, rep_bounds), indexed by global frame.
    """
    frames = fixture["frames"]
    n = len(frames)
    rate = fixture["sample_rate_hz"]
    sides_meta = fixture.get("meta", {}).get("movement_sides", [])
    frame_phases = ["RESET"] * n
    frame_side: list[str | None] = [None] * n
    rep_bounds: list[tuple[int, int]] = []

    spans = list(_spans(frames, sides_meta)) or [("Right", 0, n)]
    for side, a, b in spans:
        sub = frames[a:b]
        stream = SkeletonStream(
            sample_rate_hz=rate,
            frames=[Frame(frame_index=k, t_s=sub[k]["t_s"],
                          keypoints=[tuple(kp) for kp in sub[k]["keypoints"]])
                    for k in range(len(sub))],
        )
        res = interpret(_spec_for_side(spec, side), stream)
        base = sub[0]["t_s"]
        for k, ph in enumerate(res.frame_phases):
            frame_phases[a + k] = ph.value
            frame_side[a + k] = side
        for r in res.reps:
            sf = a + int(round((r.start_s - base) * rate))
            ef = a + int(round((r.end_s - base) * rate))
            rep_bounds.append((max(a, sf), min(b - 1, ef)))
    rep_bounds.sort()
    return frame_phases, frame_side, rep_bounds


# MediaPipe indices for each arm's wrist + elbow.
_ARM_JOINTS = {"left": (15, 13), "right": (16, 14)}


def arm_visibility(frames: list, side: str) -> float:
    """Median wrist+elbow visibility for `side` arm (0..1)."""
    wrist, elbow = _ARM_JOINTS[side]
    vis = sorted((f["keypoints"][wrist][2] + f["keypoints"][elbow][2]) / 2 for f in frames)
    return vis[len(vis) // 2] if vis else 0.0


def arm_visible(frames: list, side: str, gate: float = 0.5) -> bool:
    return arm_visibility(frames, side) >= gate


# Confidence-adaptive smoothing: a low-visibility (occluded) arm's keypoints still
# track its motion but are noisy; a heavier S-G window denoises them so reps are
# recovered instead of inflated. Validated on Bicep Curl 8 (left arm vis 0.12:
# window 9 -> 24 phantom reps; window 15 -> 13, the true count).
VIS_GATE = 0.5          # below this an arm is "estimated" (occluded)
OCCLUDED_WINDOW = 15    # S-G window for an estimated arm


def window_for(visibility: float, base_window: int) -> int:
    return base_window if visibility >= VIS_GATE else max(base_window, OCCLUDED_WINDOW)


def interpret_arm(fixture: dict, spec, joint: str, window: int | None = None):
    """Run the interpreter on ONE wrist over the whole clip (label-free).

    Returns (frame_phases: list[str], rep_bounds: list[(start_frame, end_frame)]).
    """
    frames = fixture["frames"]
    rate = fixture["sample_rate_hz"]
    stream = SkeletonStream(
        sample_rate_hz=rate,
        frames=[Frame(frame_index=k, t_s=frames[k]["t_s"],
                      keypoints=[tuple(kp) for kp in frames[k]["keypoints"]])
                for k in range(len(frames))],
    )
    upd = {"signal": spec.signal.model_copy(update={"joint": joint})}
    if window is not None:
        upd["smoothing"] = spec.smoothing.model_copy(update={"window_frames": window})
    s = spec.model_copy(update=upd)
    res = interpret(s, stream)
    phases = [p.value for p in res.frame_phases]
    bounds = [(int(round(r.start_s * rate)), int(round(r.end_s * rate))) for r in res.reps]
    return phases, bounds


def iter_annotated_frames(fixture: dict, spec, video: Path | None = None,
                          canvas: tuple[int, int] | None = None, dual: bool = True):
    """Yield (i, annotated_bgr_frame, info) for each frame. `canvas`=(w,h) letterboxes.

    dual=True tracks BOTH wrists independently (each arm tinted by its own phase,
    L/R rep counters). dual=False uses the per-movement-side path (active wrist).
    """
    frames = fixture["frames"]
    n = len(frames)
    rate = fixture["sample_rate_hz"]
    exercise = spec.display_name
    dt = 1.0 / rate

    if dual:
        # Track BOTH arms. An occluded arm (low visibility) still has its motion
        # in the data — just noisy — so denoise it with a heavier window
        # (confidence-adaptive smoothing) and flag it "(est)" rather than dropping it.
        lvis, rvis = arm_visibility(frames, "left"), arm_visibility(frames, "right")
        base = spec.smoothing.window_frames
        left_est, right_est = lvis < VIS_GATE, rvis < VIS_GATE
        lph, lreps = interpret_arm(fixture, spec, "left_wrist", window_for(lvis, base))
        rph, rreps = interpret_arm(fixture, spec, "right_wrist", window_for(rvis, base))
        left_on = right_on = True  # always rendered now; estimated arms flagged
        info = {"left_reps": len(lreps), "right_reps": len(rreps),
                "left_on": left_on, "right_on": right_on,
                "left_est": left_est, "right_est": right_est, "rate": rate}
    else:
        frame_phases, frame_side, rep_bounds = interpret_timeline(fixture, spec)
        info = {"rep_total": len(rep_bounds), "rate": rate}

    cap = None
    if video is not None and Path(video).exists():
        cap = cv2.VideoCapture(str(video))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    else:
        w, h = canvas if canvas else CANVAS

    ltut = rtut = tut = 0.0
    for i in range(n):
        if cap is not None:
            cap.set(cv2.CAP_PROP_POS_MSEC, frames[i]["t_s"] * 1000.0)
            ok, bg = cap.read()
            img = cv2.addWeighted(bg, 0.55, np.zeros_like(bg), 0, 0) if ok else np.full((h, w, 3), 30, np.uint8)
        else:
            img = np.full((h, w, 3), 30, np.uint8)

        if dual:
            lp, rp = lph[i], rph[i]
            if lp != "RESET":
                ltut += dt
            if rp != "RESET":
                rtut += dt
            ln = sum(1 for s, _ in lreps if s <= i)
            rn = sum(1 for s, _ in rreps if s <= i)
            # estimated (occluded) arms draw at a low threshold so they still show
            draw_skeleton_dual(img, frames[i]["keypoints"], left_phase=lp, right_phase=rp,
                               left_thresh=0.05 if left_est else 0.3,
                               right_thresh=0.05 if right_est else 0.3)
            draw_hud_dual(img, exercise=exercise, left=(ln, lp, ltut), right=(rn, rp, rtut),
                          left_est=left_est, right_est=right_est)
            draw_timeline_dual(img, left_phases=lph, right_phases=rph,
                               left_reps=lreps, right_reps=rreps, cur_frame=i)
            for s, e in lreps + rreps:
                if i in (s, e):
                    cv2.rectangle(img, (2, 2), (img.shape[1] - 2, img.shape[0] - 2), (60, 240, 60), 6)
        else:
            ph = frame_phases[i]
            if ph != "RESET":
                tut += dt
            rep_num = sum(1 for s, _ in rep_bounds if s <= i)
            draw_skeleton(img, frames[i]["keypoints"], active_side=frame_side[i], phase=ph)
            draw_hud(img, exercise=exercise, rep_num=min(rep_num, len(rep_bounds)),
                     rep_total=len(rep_bounds), phase=ph, tut_s=tut, side=frame_side[i])
            draw_timeline(img, frame_phases=frame_phases, rep_bounds=rep_bounds, cur_frame=i)
            for s, e in rep_bounds:
                if i in (s, e):
                    cv2.rectangle(img, (2, 2), (img.shape[1] - 2, img.shape[0] - 2), (60, 240, 60), 6)

        if canvas:
            img = letterbox(img, canvas[0], canvas[1])
        yield i, img, info
    if cap is not None:
        cap.release()


def render(fixture: dict, spec, video: Path | None, out: Path, png_frame: int | None,
           dual: bool = True):
    rate = fixture["sample_rate_hz"]
    writer = None
    last = None
    for i, img, info in iter_annotated_frames(fixture, spec, video, dual=dual):
        if png_frame is not None:
            if i == png_frame:
                out.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(out), img)
                print(f"wrote frame {i} -> {out}")
                return
            continue
        if writer is None:
            out.parent.mkdir(parents=True, exist_ok=True)
            h, w = img.shape[:2]
            writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), rate, (w, h))
        writer.write(img)
        last = info
    if writer is not None:
        writer.release()
        if dual:
            lt = f"L {last['left_reps']}" + (" est" if last.get("left_est") else "")
            rt = f"R {last['right_reps']}" + (" est" if last.get("right_est") else "")
            tag = f"{lt} / {rt}"
        else:
            tag = f"{last['rep_total']} reps"
        print(f"wrote mp4 -> {out}  ({tag} @ {rate}Hz)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, type=Path)
    ap.add_argument("--video", type=Path, default=None)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[2] / "server" / "exercises" / "db_curl.json")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--png-frame", type=int, default=None,
                    help="dump a single annotated frame index to --out (PNG) instead of mp4")
    ap.add_argument("--single-arm", action="store_true",
                    help="track only the active wrist per movement-side span (default: both arms)")
    args = ap.parse_args()

    fixture = json.loads(args.fixture.read_text())
    spec = load_spec(args.spec)
    render(fixture, spec, args.video, args.out, args.png_frame, dual=not args.single_arm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
