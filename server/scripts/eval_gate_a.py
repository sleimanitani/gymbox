"""Run Gate A over real-data fixtures and report detection quality.

Loads every fixture JSON in a directory (built by build_fixtures.py), runs the
Python reference interpreter with a spec (db_curl by default), and prints a
per-video + aggregate table of rep-count error and frame-phase agreement — the
two Gate-A metrics (architecture.md §10; bar: rep error <= 1, agreement >= 0.85).

Unlike the synthetic-fixture Gate A test, this is the REAL signal: it tells us
whether db_curl is actually tuned, and is the objective the offline fitter will
maximise. Run with the server env:

    server/.venv/bin/python server/scripts/eval_gate_a.py --fixtures data/fixtures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gymbox.dsl import PhaseLabel, load_spec
from gymbox.pipeline.metrics import score_gate_a
from gymbox.pipeline.rep import interpret
from gymbox.pipeline.types import Frame, SkeletonStream


def _stream(d: dict) -> SkeletonStream:
    frames = [
        Frame(frame_index=f["frame_index"], t_s=f["t_s"],
              keypoints=[tuple(kp) for kp in f["keypoints"]])
        for f in d["frames"]
    ]
    return SkeletonStream(sample_rate_hz=d["sample_rate_hz"], frames=frames)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--spec", type=Path,
                    default=Path(__file__).parents[1] / "exercises" / "db_curl.json")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    files = sorted(args.fixtures.glob("*.json"))
    if not files:
        print(f"no fixtures in {args.fixtures}")
        return 1

    print(f"spec: {args.spec.name}   fixtures: {len(files)}\n")
    hdr = f"{'video':24s} {'frames':>6} {'reps_true':>9} {'reps_pred':>9} {'rep_err':>7} {'phase_agr':>9} {'sides':>16} {'gate':>5}"
    print(hdr); print("-" * len(hdr))

    tot_err = 0
    tot_match = 0.0
    tot_frames = 0
    n_pass = 0
    for f in files:
        d = json.loads(f.read_text())
        stream = _stream(d)
        truth_phases = [PhaseLabel(p) for p in d["labels"]["frame_phases"]]
        truth_reps = int(d["labels"]["rep_count"])
        res = interpret(spec, stream)
        rep = score_gate_a(res, true_rep_count=truth_reps, true_frame_phases=truth_phases)
        sides = sorted({s["value"] for s in d.get("meta", {}).get("movement_sides", [])})
        passed = rep.passes_gate_a()
        n_pass += passed
        tot_err += rep.rep_count_error
        tot_match += rep.frame_phase_agreement * rep.n_frames
        tot_frames += rep.n_frames
        print(f"{d['name']:24s} {len(stream):>6} {truth_reps:>9} {res.rep_count:>9} "
              f"{rep.rep_count_error:>7} {rep.frame_phase_agreement:>9.3f} "
              f"{str(sides):>16} {'PASS' if passed else 'FAIL':>5}")

    print("-" * len(hdr))
    micro = tot_match / tot_frames if tot_frames else 0.0
    print(f"AGGREGATE: {n_pass}/{len(files)} pass Gate A | mean rep-err "
          f"{tot_err/len(files):.2f} | micro phase-agreement {micro:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
