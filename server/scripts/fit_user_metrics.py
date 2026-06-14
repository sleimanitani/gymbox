"""Fit db_curl to USER-IMPACTFUL metrics (reps + TUT), with per-metric calibration.

Unlike fit_db_curl.py (which maximizes frame-phase agreement), this optimizes the
metrics a user actually sees, with configurable weights:

  - rep_count error      (weight --w-rep,  default 2.0)
  - dynamic TUT  (CON+ECC time)  error  (weight --w-dyn, default 2.0)
  - active  TUT  (non-RESET time) error (weight --w-act, default 1.0)

Per-metric CALIBRATION: each TUT gets a global de-bias scale (the first rung of
the global -> per-camera -> per-user ladder). For every candidate spec we compute
the optimal scale s* = sum(labeled)/sum(predicted) and score the *post-calibration*
residual — because that scale is a parameter we will ship. The fitter therefore
picks spec params that are easiest to calibrate, not just lowest raw error.

Evaluation is per-side (active wrist), since the videos alternate arms.

    server/.venv/bin/python server/scripts/fit_user_metrics.py --fixtures data/fixtures
    ... --w-rep 3 --w-dyn 2 --w-act 1      # reweight toward rep count
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

from gymbox.dsl.models import ExerciseSpec
from gymbox.pipeline.rep import interpret
from gymbox.pipeline.types import Frame, SkeletonStream

MIN_SPAN = 15
DT = 1 / 15.0
ABS_V = [0.05, 0.06, 0.07, 0.08, 0.10]
WINDOW = [7, 9, 11]
MIN_AMP = [0.06, 0.08, 0.10]
PROM = [0.25, 0.30, 0.35]


def _side_at(t, sides):
    for s in sides:
        if s["start"] <= t < s["end"]:
            return s["value"]
    return None


def _spans(frames, sides):
    cur, st0 = None, 0
    for i, f in enumerate(frames):
        sd = _side_at(f["t_s"], sides)
        if sd != cur:
            if cur in ("Left", "Right", "Both") and i - st0 >= MIN_SPAN:
                yield cur, list(range(st0, i))
            cur, st0 = sd, i
    if cur in ("Left", "Right", "Both") and len(frames) - st0 >= MIN_SPAN:
        yield cur, list(range(st0, len(frames)))


def _con_runs(ph):
    n, p = 0, None
    for x in ph:
        if x == "CON" and p != "CON":
            n += 1
        p = x
    return n


def _spec_for_side(spec, side):
    j = "left_wrist" if side == "Left" else "right_wrist"
    if spec.signal.joint == j:
        return spec
    return spec.model_copy(update={"signal": spec.signal.model_copy(update={"joint": j})})


def make_spec(base: dict, abs_v: float, window: int, min_amp: float, prom: float) -> ExerciseSpec:
    d = json.loads(json.dumps(base))
    d["smoothing"]["window_frames"] = window
    d["rep"]["min_amplitude"] = min_amp
    d["rep"]["prominence_frac"] = prom
    d["phase"] = {
        "default": "RESET",
        "rules": [
            {"label": "RESET", "when": {"abs_v_lt": abs_v, "position_band": "high"}},
            {"label": "ISO_UNLOADED", "when": {"abs_v_lt": abs_v, "position_band": "low"}},
            {"label": "CON", "when": {"abs_v_gt": abs_v, "direction": "toward_high"}},
            {"label": "ECC", "when": {"abs_v_gt": abs_v, "direction": "toward_low"}},
        ],
    }
    return ExerciseSpec.model_validate(d)


def collect(spec: ExerciseSpec, fixtures: list[dict]):
    """Per-span (lab_reps, pred_reps, lab_dyn, pred_dyn, lab_act, pred_act)."""
    rows = []
    for d in fixtures:
        frames = d["frames"]
        ph = d["labels"]["frame_phases"]
        sides = d.get("meta", {}).get("movement_sides", [])
        for side, idxs in _spans(frames, sides):
            sub = [frames[i] for i in idxs]
            stream = SkeletonStream(
                sample_rate_hz=15.0,
                frames=[Frame(frame_index=k, t_s=sub[k]["t_s"],
                              keypoints=[tuple(kp) for kp in sub[k]["keypoints"]])
                        for k in range(len(sub))],
            )
            res = interpret(_spec_for_side(spec, side), stream)
            lab = [ph[i] for i in idxs]
            pred = [p.value for p in res.frame_phases]
            rows.append((
                _con_runs(lab), res.rep_count,
                sum(x in ("CON", "ECC") for x in lab) * DT,
                sum(x in ("CON", "ECC") for x in pred) * DT,
                sum(x != "RESET" for x in lab) * DT,
                sum(x != "RESET" for x in pred) * DT,
            ))
    return rows


def _tut_metric(rows, li, pi):
    pairs = [(r[li], r[pi]) for r in rows if r[li] > 0]
    scale = sum(l for l, _ in pairs) / sum(p for _, p in pairs)
    raw = st.median([abs(p - l) / l for l, p in pairs])
    cal = st.median([abs(scale * p - l) / l for l, p in pairs])
    return scale, raw, cal


def score(rows):
    lab_r = sum(r[0] for r in rows)
    pred_r = sum(r[1] for r in rows)
    rep_err = abs(pred_r - lab_r) / lab_r
    dyn_scale, dyn_raw, dyn_cal = _tut_metric(rows, 2, 3)
    act_scale, act_raw, act_cal = _tut_metric(rows, 4, 5)
    return {
        "rep_err": rep_err,
        "dyn_scale": dyn_scale, "dyn_raw": dyn_raw, "dyn_cal": dyn_cal,
        "act_scale": act_scale, "act_raw": act_raw, "act_cal": act_cal,
    }


def objective(m, w_rep, w_dyn, w_act):
    # weighted average of the post-calibration user-metric errors
    return (w_rep * m["rep_err"] + w_dyn * m["dyn_cal"] + w_act * m["act_cal"]) / (w_rep + w_dyn + w_act)


def fmt(m):
    return (f"rep {100*m['rep_err']:4.1f}% | dyn {100*m['dyn_raw']:4.1f}->{100*m['dyn_cal']:4.1f}% (x{m['dyn_scale']:.3f}) "
            f"| act {100*m['act_raw']:4.1f}->{100*m['act_cal']:4.1f}% (x{m['act_scale']:.3f})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[1] / "exercises" / "db_curl.json")
    ap.add_argument("--w-rep", type=float, default=2.0)
    ap.add_argument("--w-dyn", type=float, default=2.0)
    ap.add_argument("--w-act", type=float, default=1.0)
    args = ap.parse_args()

    base = json.loads(args.spec.read_text())
    fixtures = [json.loads(f.read_text()) for f in sorted(args.fixtures.glob("*.json"))]

    cur = score(collect(ExerciseSpec.model_validate(base), fixtures))
    print(f"weights: rep={args.w_rep} dyn={args.w_dyn} act={args.w_act}   (errors are per-span median; raw->calibrated)\n")
    print(f"CURRENT db_curl:  {fmt(cur)}   obj={objective(cur,args.w_rep,args.w_dyn,args.w_act):.4f}\n")

    results = []
    for w in WINDOW:
        for a in ABS_V:
            for ma in MIN_AMP:
                for pr in PROM:
                    m = score(collect(make_spec(base, a, w, ma, pr), fixtures))
                    results.append((objective(m, args.w_rep, args.w_dyn, args.w_act), m, (a, w, ma, pr)))
    results.sort(key=lambda r: r[0])

    print(f"{'rank':>4} {'abs_v':>5} {'win':>3} {'minamp':>6} {'prom':>4}   metrics")
    print("-" * 92)
    for i, (obj, m, p) in enumerate(results[:8]):
        print(f"{i+1:>4} {p[0]:>5.2f} {p[1]:>3} {p[2]:>6.2f} {p[3]:>4.2f}   {fmt(m)}  obj={obj:.4f}")
    best = results[0]
    print(f"\nBEST params: abs_v={best[2][0]} window={best[2][1]} min_amp={best[2][2]} prom={best[2][3]}")
    print(f"  -> {fmt(best[1])}")
    print(f"  calibration scales to ship (global): dynamic x{best[1]['dyn_scale']:.3f}, active x{best[1]['act_scale']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
