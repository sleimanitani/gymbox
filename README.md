# gymbox

A B2B computer-vision library for **gym exercise tracking**, licensed to
integrators (gym software vendors, fitness apps, connected-equipment makers).
Point a phone camera at someone lifting and gymbox reports what they did:
exercise, reps, per-rep phase (concentric / eccentric / isometric holds), weight,
and side. It is a **set of libraries**, not an end-user app — integrators embed
it in their own products under their own brand.

> **Status:** MVP-α scaffold. Architecture locked at v0.7 (`docs/architecture.md`).
> One exercise (dumbbell bicep curl), a heuristic DSL detector, full
> phone → server upload path. Several components are concrete; the rep
> interpreter and its Swift port are the headline work. See `docs/ROADMAP.md`.

---

## Architecture in one breath

**Edge-first.** The phone runs all real-time inference (MediaPipe Pose Lite +
a Swift interpreter of a small JSON exercise spec), buffers sessions locally, and
uploads skeleton frames + annotations on Wi-Fi. The server is **dumb storage** +
an `/exercises` over-the-air spec channel. No gRPC service, no streaming pipeline
in MVP-α. The Python `pipeline/` is a **reference oracle** (golden reference for
the Swift port + batch replay), not a runtime component. The exercise spec itself
is produced **offline** by a fitter (the offline ML): labeled videos → fitted
thresholds/bands/smoothing → human audit → OTA. The phone runtime stays pure
heuristic.

## What's in this repo

| Path | What |
|---|---|
| `gymbox-proto/` | The upload-envelope wire format (Protocol Buffers) + Python & Swift bindings. No service definition. |
| `server/` | The `gymbox` Python package: FastAPI router, Postgres persistence, the OTA spec channel, the reference rep-detection oracle, Alembic migrations, tests. |
| `ios/` | `GymboxSDK` — the Swift package that runs on the phone: pose intake, on-device interpreter, local recording, Wi-Fi upload, OTA spec cache. Zero UI. |
| `gymbox-box/` | A reference Docker deployment (Postgres + the library behind nginx) for demos and evaluation. Not production. |
| `docs/` | `architecture.md`, `product.md`, `ROADMAP.md`, `CLAUDE.md`, `WORKLOG.md` (active plans + progress + session index), `NOTES.md`, `TRACKER.md`, `SETUP.md`. |

## Quick start

```bash
# Python server + tests
cd server
pip install -e ".[dev]"
python scripts/make_fixture.py     # synthetic bicep_curl_1 fixture
pytest -q                          # DSL/signal/etag pass; Gate A xfails; ingest skips
```

Full instructions for every package (proto, iOS, reference box, migrations) are
in **`docs/SETUP.md`**.

## The two gates

Correctness is split into two ordered gates (`docs/architecture.md` §10):

- **Gate A — acceptance.** The Python interpreter vs human labels on the
  `bicep_curl_1` fixture: rep-count error ≤ 1, frame-phase agreement ≥ 85%. The
  real MVP-α bar. Passes **first**.
- **Gate B — port regression.** The Swift interpreter vs the Python oracle:
  ≥ 98% frame-phase identity, identical rep count, ±2-frame boundaries. Isolates
  "the port drifted" from "the spec is mistuned".

The offline fitter (dev-machine tooling, planned at `server/gymbox/fitter/`)
optimizes Gate A: it searches the locked DSL grammar for the spec values that
maximize the Python interpreter's score against human labels.

## For Claude Code

Start with **`docs/CLAUDE.md`** — it has the build order, the do-not list, and
the gate definitions — then **`docs/WORKLOG.md`** for the active plans, their live
progress, and the index of past sessions (read this first to resume work safely
across sessions/crashes). The immediate milestone is `server/gymbox/pipeline/rep.py`
(ROADMAP Step 3 / Gate A): the signal front-end and phase evaluator are provided;
implement extrema-pair rep detection and per-frame phase labeling.

## Licensing & data

gymbox is licensed per-integrator. Everything it collects lives in the
integrator's infrastructure — there is no central gymbox cloud aggregating user
data. Specs and (later) models flow the other way, via the OTA channel. See
`docs/product.md`.
