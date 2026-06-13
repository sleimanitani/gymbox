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
| `gymbox.pipeline.rep.interpret` | **concrete** | **Gate A PASSES** on synthetic fixture (rep err 0, agreement 0.884) |
| `gymbox.pipeline.{activity,fsm,classifier,camera_angle,replay}` | stubs | reserved |
| `gymbox.materializer` | **concrete** | annotations → sets/reps |
| `gymbox.refdeploy` | **concrete** | reference box only |
| `exercises/db_curl.json` | **locked** | the MVP-α spec |
| Alembic migration 0001 | **present** | schema + 13 layers, from metadata |
| Tests: DSL / signal / etag | **passing** | pure-unit |
| Tests: Gate A | **passing** | on synthetic fixture (see note under Gates) |
| Tests: ingest | **passing** (Postgres-gated) | fixed stale read-API calls; skips without `GYMBOX_TEST_DB` |
| Tests: integration (Step 9) | **passing** (Postgres-gated) | end-to-end round-trip: detect → upload → materialize → read back 8 reps |
| `Database.seed_reference_data()` | **concrete** | seeds 13 annotation-layer FK rows for `create_all()` setups (ref-box + tests); prod uses Alembic |
| iOS `Signal` + `evaluatePhase` + `DynamicBands` | **concrete** | mirrors Python |
| iOS `DSLInterpreter.interpret` | **concrete** | **Gate B PASSES** — exact parity with Python oracle (100% identity, 8/8 reps, 0-frame dev) |
| iOS Pose / Recording / Upload / Catalog | **concrete** | `reinterpret()` done (Step 8) — rep/rep_phase annotations, deterministic ids, idempotent |
| `gymbox-box` (Compose) | **present** | verify round-trip — Step 10 |

## Gates

- **Gate A** (acceptance, Python vs human labels): rep error ≤ 1, frame-phase
  agreement ≥ 85%. Status: **PASSES** on the synthetic `bicep_curl_1` fixture —
  rep error 0 (8/8), agreement 0.884. ⚠️ This proves the *interpreter plumbing*,
  not the *tuning*: the fixture is synthetic (NOTES.md). The residual ~12%
  disagreement is dominated by the lead-in/trailing RESET frames, which the
  generator labels RESET while the arm sits at the bottom (low band) so the
  interpreter calls them ISO_LOADED — a label-convention artifact, not a tuning
  error. Re-run on a real human-labelled capture before trusting the number.
- **Gate B** (port regression, Swift vs Python): ≥ 98% frame-phase identity,
  identical rep count, ±2-frame boundaries. Status: **PASSES** — the Swift port
  reproduces the Python oracle exactly on `bicep_curl_1`: 100% frame-phase
  identity, 8/8 rep count, 0-frame max boundary deviation. Verified by compiling
  the 5 DSL sources with `swiftc` against the bundled golden output
  (`oracle_bicep_curl_1.json`); the XCTest `testGateB_matchesPythonOracle`
  encodes the same comparison for CI/Xcode. (Full `swift test` can't link on this
  Linux box — the SDK target's URLSession files need FoundationNetworking +
  libcurl-dev, no sudo — so the DSL path is verified standalone.)
- **Integration / "MVP-α done"** (ROADMAP Step 9): a detected session round-trips
  into Postgres and reads back materialized. Status: **PASSES** — `interpret` →
  upload envelope → `ingest_session` → `materialize` → `read_session` returns one
  set with all 8 reps, each carrying phase durations (`tests/test_integration.py`,
  Postgres-gated). Verified against a throwaway local PG 16 cluster. Remaining MVP-α
  loose end: Step 10 (verify `gymbox-box` Compose end-to-end) — the latent
  layer-seed gap that would have broken it is now fixed (`seed_reference_data`).

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
| 2026-06-10 | bicep_curl_1 (synthetic) | implement `rep.interpret` (zig-zag extrema + per-frame phase); db_curl.json **unchanged** | 0 | 0.884 | **Gate A PASS** (plumbing; synthetic fixture) |
| 2026-06-13 | bicep_curl_1 (oracle) | port `DSLInterpreter.swift` from rep.py (Gate B: Swift vs Python) | 0 | 1.000 | **Gate B PASS** — exact parity, 0-frame boundary dev |

## SOTA / references

_Drop links + one-line takeaways as you research rep-counting / pose-based phase
segmentation. Empty for now._
