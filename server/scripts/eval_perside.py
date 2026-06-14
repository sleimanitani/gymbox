"""Per-side Gate A evaluation on real-data fixtures.

db_curl is single-arm; the videos alternate arms. This splits each fixture into
contiguous Movement-Side spans (from meta.movement_sides), tracks the ACTIVE
wrist per span (left_wrist for "Left", right_wrist for "Right"/"Both"), and scores
Gate A on each span against the hand labels. This isolates real tuning quality
from the right-wrist-is-blind-to-the-left-arm artifact.

Ground truth per span: rep count = number of CON runs; frame phases = the labels.

    server/.venv/bin/python server/scripts/eval_perside.py --fixtures data/fixtures
    server/.venv/bin/python server/scripts/eval_perside.py --fixtures data/fixtures --spec server/exercises/db_curl.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gymbox.dsl import PhaseLabel, load_spec
from gymbox.pipeline.metrics import score_gate_a
from gymbox.pipeline.rep import interpret
from gymbox.pipeline.types import Frame, SkeletonStream

MIN_SPAN_FRAMES = 15


def _side_at(t: float, sides: list[dict]) -> str | None:
    for s in sides:
        if s["start"] <= t < s["end"]:
            return s["value"]
    return None


def _con_runs(phases: list[str]) -> int:
    """Number of contiguous CON runs = rep count proxy within a span."""
    n = 0
    prev = None
    for p in phases:
        if p == "CON" and prev != "CON":
            n += 1
        prev = p
    return n


def _spec_for_side(spec, side: str):
    """db_curl variant tracking the active wrist for this side-span."""
    joint = "left_wrist" if side == "Left" else "right_wrist"
    if spec.signal.joint == joint:
        return spec
    return spec.model_copy(
        update={"signal": spec.signal.model_copy(update={"joint": joint})}
    )


def _spans(frames: list[dict], sides: list[dict]):
    """Yield (side, [frame indices]) for each contiguous same-side run."""
    cur, start = None, 0
    for i, f in enumerate(frames):
        sd = _side_at(f["t_s"], sides)
        if sd != cur:
            if cur in ("Left", "Right", "Both") and i - start >= MIN_SPAN_FRAMES:
                yield cur, list(range(start, i))
            cur, start = sd, i
    if cur in ("Left", "Right", "Both") and len(frames) - start >= MIN_SPAN_FRAMES:
        yield cur, list(range(start, len(frames)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[1] / "exercises" / "db_curl.json")
    args = ap.parse_args()
    spec = load_spec(args.spec)
    files = sorted(args.fixtures.glob("*.json"))

    print(f"spec: {args.spec.name}   per-side eval over {len(files)} videos\n")
    hdr = f"{'video / side-span':30s} {'frames':>6} {'reps_t':>6} {'reps_p':>6} {'err':>4} {'phase_agr':>9} {'gate':>5}"
    print(hdr); print("-" * len(hdr))

    tot_match = tot_frames = 0.0
    n_pass = n_span = 0
    rep_errs = []
    for f in files:
        d = json.loads(f.read_text())
        frames = d["frames"]
        all_phases = d["labels"]["frame_phases"]
        sides = d.get("meta", {}).get("movement_sides", [])
        side_idx = 0
        for side, idxs in _spans(frames, sides):
            side_idx += 1
            sub = [frames[i] for i in idxs]
            # reindex frames 0..k for a clean sub-stream
            stream = SkeletonStream(
                sample_rate_hz=d["sample_rate_hz"],
                frames=[Frame(frame_index=k, t_s=sub[k]["t_s"],
                              keypoints=[tuple(kp) for kp in sub[k]["keypoints"]])
                        for k in range(len(sub))],
            )
            tphases = [all_phases[i] for i in idxs]
            treps = _con_runs(tphases)
            res = interpret(_spec_for_side(spec, side), stream)
            rep = score_gate_a(res, true_rep_count=treps,
                               true_frame_phases=[PhaseLabel(p) for p in tphases])
            passed = rep.passes_gate_a()
            n_pass += passed; n_span += 1
            rep_errs.append(rep.rep_count_error)
            tot_match += rep.frame_phase_agreement * rep.n_frames
            tot_frames += rep.n_frames
            tag = f"{d['name']}#{side_idx}({side})"
            print(f"{tag:30s} {len(stream):>6} {treps:>6} {res.rep_count:>6} "
                  f"{rep.rep_count_error:>4} {rep.frame_phase_agreement:>9.3f} {'PASS' if passed else 'FAIL':>5}")

    print("-" * len(hdr))
    micro = tot_match / tot_frames if tot_frames else 0.0
    mean_err = sum(rep_errs) / len(rep_errs) if rep_errs else 0.0
    print(f"AGGREGATE: {n_pass}/{n_span} spans pass | mean rep-err {mean_err:.2f} | micro phase-agreement {micro:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
