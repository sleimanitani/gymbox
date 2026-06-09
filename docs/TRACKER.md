# gymbox — TRACKER

Persistent state across build sessions. Update the status table and log
experiments as Gate A/B tuning happens.

---

## Component status

| Component | State | Gate / note |
|---|---|---|
| `gymbox-proto` (envelope + bindings) | scaffold complete; bindings ungenerated | Step 1 |
| `gymbox.dsl` (models, keypoints) | **concrete, locked** | — |
| `gymbox.persistence` (ORM, schema) | **concrete, locked** | 12 tables |
| `gymbox.api` (FastAPI router) | **concrete** | only API surface in MVP-α |
| `gymbox.pipeline.signal` | **concrete** | unit-tested |
| `gymbox.pipeline.rep.interpret` | **STUB** (`NotImplementedError`) | **Gate A** — Step 3 |
| `gymbox.pipeline.{activity,fsm,classifier,camera_angle,replay}` | stubs | reserved |
| `gymbox.materializer` | **concrete** | annotations → sets/reps |
| `gymbox.refdeploy` | **concrete** | reference box only |
| `exercises/db_curl.json` | **locked** | the MVP-α spec |
| Alembic migration 0001 | **present** | schema + 13 layers, from metadata |
| Tests: DSL / signal / etag | **passing** | pure-unit |
| Tests: Gate A | **xfail** | until `rep.py` |
| Tests: ingest | **skip** | until `GYMBOX_TEST_DB` |
| iOS `Signal` + `evaluatePhase` + `DynamicBands` | **concrete** | mirrors Python |
| iOS `DSLInterpreter.interpret` | **STUB** (`fatalError`) | **Gate B** — Step 7 |
| iOS Pose / Recording / Upload / Catalog | **concrete** | `reinterpret()` stubbed |
| `gymbox-box` (Compose) | **present** | verify round-trip — Step 10 |

## Gates

- **Gate A** (acceptance, Python vs human labels): rep error ≤ 1, frame-phase
  agreement ≥ 85%. Status: **not yet attempted** (interpreter unimplemented).
- **Gate B** (port regression, Swift vs Python): ≥ 98% frame-phase identity,
  identical rep count, ±2-frame boundaries. Status: **blocked on Gate A**.

## Hypotheses (db_curl tuning)

_Log here as you tune `db_curl.json`. Seed entries:_

- H1: S-G `window_frames=7, polyorder=2` at 15 Hz smooths wrist-y enough to kill
  double-counting at the top of the curl without blurring rep boundaries past the
  ±2-frame Gate B tolerance. **Untested** — needs Gate A run on a real capture.
- H2: `prominence_frac=0.30` rejects partial reps / readjustments at the bottom.
  **Untested.**
- H3: phase `abs_v` threshold `0.04` (normalized units/s) cleanly separates the
  ISO holds from CON/ECC. **Untested.**

## Experiments

_Append one row per Gate A run: fixture, spec params changed, rep error, phase
agreement, verdict._

| Date | Fixture | Change | Rep err | Phase agr | Verdict |
|---|---|---|---|---|---|
| — | (synthetic) | baseline scaffold | n/a | n/a | interpreter not yet implemented |

## SOTA / references

_Drop links + one-line takeaways as you research rep-counting / pose-based phase
segmentation. Empty for now._
