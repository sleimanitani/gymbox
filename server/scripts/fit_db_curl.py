"""Offline fitter for db_curl (architecture.md — offline spec fitting).

Searches the LOCKED DSL grammar for the spec values that best reproduce the human
labels, maximizing per-side Gate-A frame-phase agreement (subject to rep-count
staying accurate). The rule *structure* is set from the data characterization
(server/scripts/characterize_phases.py findings):

    bottom/extended slow hold -> ISO_UNLOADED   (data's convention)
    top/flexed slow pause     -> RESET
    moving toward high (fast) -> CON
    moving toward low  (fast) -> ECC
    default                   -> RESET           (ISO_LOADED unused in this data)

It searches the abs-velocity threshold and the smoothing window (both in-grammar),
prints the leaderboard, and writes the winner to the spec path with --write.

    server/.venv/bin/python server/scripts/fit_db_curl.py --fixtures data/fixtures
    server/.venv/bin/python server/scripts/fit_db_curl.py --fixtures data/fixtures --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gymbox.dsl.models import ExerciseSpec
from gymbox.pipeline.metrics import score_gate_a
from gymbox.pipeline.rep import interpret
from gymbox.pipeline.types import Frame, PhaseLabel, SkeletonStream

MIN_SPAN_FRAMES = 15
T_GRID = [0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12]
WINDOW_GRID = [5, 7, 9, 11]
MAX_MEAN_REP_ERR = 0.5  # keep rep detection accurate while tuning phases


def data_aligned_phase_rules(t: float) -> dict:
    return {
        "default": "RESET",
        "rules": [
            {"label": "RESET", "when": {"abs_v_lt": t, "position_band": "high"}},
            {"label": "ISO_UNLOADED", "when": {"abs_v_lt": t, "position_band": "low"}},
            {"label": "CON", "when": {"abs_v_gt": t, "direction": "toward_high"}},
            {"label": "ECC", "when": {"abs_v_gt": t, "direction": "toward_low"}},
        ],
    }


def make_spec(base: dict, t: float, window: int) -> ExerciseSpec:
    d = json.loads(json.dumps(base))  # deep copy
    d["smoothing"]["window_frames"] = window
    d["phase"] = data_aligned_phase_rules(t)
    return ExerciseSpec.model_validate(d)


def _side_at(t, sides):
    for s in sides:
        if s["start"] <= t < s["end"]:
            return s["value"]
    return None


def _spans(frames, sides):
    cur, start = None, 0
    for i, f in enumerate(frames):
        sd = _side_at(f["t_s"], sides)
        if sd != cur:
            if cur in ("Left", "Right", "Both") and i - start >= MIN_SPAN_FRAMES:
                yield cur, list(range(start, i))
            cur, start = sd, i
    if cur in ("Left", "Right", "Both") and len(frames) - start >= MIN_SPAN_FRAMES:
        yield cur, list(range(start, len(frames)))


def _con_runs(phases):
    n, prev = 0, None
    for p in phases:
        if p == "CON" and prev != "CON":
            n += 1
        prev = p
    return n


def _spec_for_side(spec, side):
    joint = "left_wrist" if side == "Left" else "right_wrist"
    if spec.signal.joint == joint:
        return spec
    return spec.model_copy(update={"signal": spec.signal.model_copy(update={"joint": joint})})


def evaluate(spec: ExerciseSpec, fixtures: list[dict]) -> tuple[float, float, int, int]:
    """Return (micro_phase_agreement, mean_rep_err, n_pass, n_span)."""
    tot_match = tot_frames = 0.0
    rep_errs = []
    n_pass = n_span = 0
    for d in fixtures:
        frames = d["frames"]
        all_phases = d["labels"]["frame_phases"]
        sides = d.get("meta", {}).get("movement_sides", [])
        for side, idxs in _spans(frames, sides):
            sub = [frames[i] for i in idxs]
            stream = SkeletonStream(
                sample_rate_hz=d["sample_rate_hz"],
                frames=[Frame(frame_index=k, t_s=sub[k]["t_s"],
                              keypoints=[tuple(kp) for kp in sub[k]["keypoints"]])
                        for k in range(len(sub))],
            )
            tphases = [all_phases[i] for i in idxs]
            res = interpret(_spec_for_side(spec, side), stream)
            rep = score_gate_a(res, true_rep_count=_con_runs(tphases),
                               true_frame_phases=[PhaseLabel(p) for p in tphases])
            n_span += 1
            n_pass += rep.passes_gate_a()
            rep_errs.append(rep.rep_count_error)
            tot_match += rep.frame_phase_agreement * rep.n_frames
            tot_frames += rep.n_frames
    micro = tot_match / tot_frames if tot_frames else 0.0
    mean_err = sum(rep_errs) / len(rep_errs) if rep_errs else 0.0
    return micro, mean_err, n_pass, n_span


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[1] / "exercises" / "db_curl.json")
    ap.add_argument("--write", action="store_true", help="write the winning spec back")
    args = ap.parse_args()

    base = json.loads(args.spec.read_text())
    fixtures = [json.loads(f.read_text()) for f in sorted(args.fixtures.glob("*.json"))]

    results = []
    for window in WINDOW_GRID:
        for t in T_GRID:
            spec = make_spec(base, t, window)
            micro, mean_err, n_pass, n_span = evaluate(spec, fixtures)
            results.append((micro, mean_err, n_pass, n_span, t, window))

    feasible = [r for r in results if r[1] <= MAX_MEAN_REP_ERR]
    ranked = sorted(feasible or results, key=lambda r: -r[0])
    print(f"{'rank':>4} {'abs_v':>6} {'window':>6} {'phase_agr':>9} {'mean_rep_err':>12} {'pass':>8}")
    print("-" * 52)
    for i, (micro, err, np_, ns, t, w) in enumerate(ranked[:10]):
        print(f"{i+1:>4} {t:>6.2f} {w:>6} {micro:>9.3f} {err:>12.2f} {np_:>3}/{ns:<4}")

    best = ranked[0]
    print(f"\nBEST: abs_v={best[4]} window={best[5]} -> phase-agreement {best[0]:.3f}, "
          f"mean rep-err {best[1]:.2f}, {best[2]}/{best[3]} spans pass")

    if args.write:
        winner = make_spec(base, best[4], best[5])
        out = json.loads(winner.model_dump_json(exclude_none=True))
        args.spec.write_text(json.dumps(out, indent=2) + "\n")
        print(f"\nwrote winner to {args.spec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
