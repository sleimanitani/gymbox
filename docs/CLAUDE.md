# CLAUDE.md — instructions for Claude Code working on gymbox

You are developing **gymbox**, a B2B computer-vision library for gym exercise
tracking, licensed to integrators (gym software vendors, fitness apps, equipment
makers). It is a set of libraries/packages, **not** an end-user app. Sol owns the
architecture; you implement against it.

Read `docs/architecture.md` (v0.7, locked for MVP-α) and `docs/product.md` first.
This file is the operational summary: what to build, in what order, and — equally
important — **what not to do**.

**Before doing any work, read `docs/WORKLOG.md`** — it holds the active plans and
their live progress across sessions, and the index of past (including crashed)
sessions. Follow its operating protocol: write a plan before you act, tick each
step as you complete it. A crashed session is recoverable only because the
WORKLOG reflects on-disk reality at all times. When a session ends or crashes,
the next one resumes from the first unchecked step there.

---

## The one-paragraph mental model

The **phone** runs all real-time inference: MediaPipe Pose Lite emits a 33-joint
skeleton, the Swift `DSLInterpreter` *executes* a small JSON exercise spec on
that skeleton stream to detect reps/phases live, sessions buffer locally, and
skeleton frames + annotations upload on Wi-Fi. The **server** is dumb storage +
an `/exercises` OTA spec channel. The JSON spec itself is produced by an
**offline fitter** on a dev machine: labeled videos in, fitted thresholds /
bands / smoothing out, human-audited, shipped via OTA. There is **no gRPC
service and no streaming pipeline in MVP-α** — `gymbox-proto` defines only the
upload envelope. The Python `pipeline/` is a **reference oracle** (golden
reference for the Swift port + batch replay), **not a runtime component**; the
offline fitter is dev-machine tooling, also not a runtime component.

---

## What "interpreter" and "spec" mean (no jargon)

The **spec** is data — `server/exercises/db_curl.json`. It declares which
joints to watch, smoothing parameters, and the phase/rep rules (angle bands,
thresholds, direction predicates). It is *not* a model.

The **interpreter** is the code that reads the spec and executes it against a
live skeleton stream — a config-driven state machine. For each frame it emits
a phase label; over a stream it emits reps. Two copies exist, by design:

- `server/gymbox/pipeline/rep.py` — Python "oracle" (offline; golden reference
  for the port and for batch replay over uploaded sessions).
- `ios/.../DSLInterpreter.swift` — the on-device Swift port that the phone runs
  in real time.

Same spec → both interpreters produce the same answer. That equivalence is
exactly what Gate B measures.

---

## Offline spec fitting (where ML lives)

Where do the thresholds, bands, smoothing windows, and direction predicates in
`db_curl.json` come from? **They are fitted offline, from labeled videos.**
The flow:

```
labeled videos ──► offline fitter ──► exercise spec JSON ──► human audit ──► OTA
   (skeleton          (parameter           (e.g.               (sanity-              (phones
    JSON +             search over the     db_curl.json)       check on              pick up
    ground-truth       locked DSL                              held-out              the new
    phase + rep        grammar; objective                      clips)                spec on
    labels per         = maximize Gate-A                                              next
    frame)             score on the                                                   launch)
                       training set)
```

Important distinctions:

- The fitter runs on a **dev machine**, not in the running server and not on
  the phone. Its output is a JSON spec — a heuristic specification, not a
  learned model.
- The **phone runtime stays pure heuristic**. The interpreter executes the
  fitted spec; it does not call torch/onnxruntime. The "no runtime ML" rule
  below refers to the phone + ingest path only.
- The optional `model_spec` field on `ExerciseSpec` (architecture.md §11.2) is
  a *separate*, later concept: a learned per-exercise classifier head that
  could run on-device alongside the heuristic interpreter. Reserved for
  MVP-β+; null in MVP-α.
- **The fitter optimizes Gate A** (Python interpreter vs. human labels on the
  held-out fixture). It does not invent grammar — the spec grammar is locked
  (architecture.md §10); the fitter chooses values within it.
- Where it will live: `server/gymbox/fitter/` (planned; not in the initial
  commit). Inputs: paired skeleton + label JSON files. Output: an
  `ExerciseSpec`-compatible JSON dict.

---

## Repository layout

```
gymbox-proto/      upload-envelope schema (proto) + Python & Swift bindings
server/            the `gymbox` Python package (storage + OTA + reference oracle)
  gymbox/dsl/        DSL Pydantic models + keypoint registry   [CONCRETE, LOCKED]
  gymbox/persistence/ SQLAlchemy 2.x async ORM, schema         [CONCRETE, LOCKED]
  gymbox/api/        FastAPI router (the only API surface)     [CONCRETE]
  gymbox/pipeline/   reference oracle: signal + rep + metrics  [signal CONCRETE; rep STUB]
  gymbox/materializer.py  annotations -> sets/reps             [CONCRETE]
  gymbox/refdeploy.py     reference-box app factory            [CONCRETE]
  exercises/db_curl.json  the locked MVP-α spec                [LOCKED]
  tests/                  DSL/signal/etag/ingest/Gate A        [present]
  migrations/             Alembic; 0001 creates schema+seeds   [present]
ios/               GymboxSDK Swift package
  Sources/GymboxSDK/DSL/   spec types + Signal + DSLInterpreter [signal CONCRETE; interpret STUB]
  Sources/GymboxSDK/...    Pose / Recording / Upload / Catalog  [CONCRETE except reinterpret]
gymbox-box/        reference Docker deployment (demo only)
docs/              architecture.md, product.md, ROADMAP.md, NOTES.md, TRACKER.md, SETUP.md
```

`[LOCKED]` = do not change the design; implement against it. If you think a
locked decision is wrong, write it in `docs/NOTES.md` and keep going — don't
silently diverge.

---

## Build order (and the two gates)

Follow `docs/ROADMAP.md`. The critical path and its acceptance bars:

1. **Proto bindings** — generate Python + Swift from `gymbox-proto/proto`.
2. **(done) DSL + persistence + API + signal front-end** — already concrete.
3. **`server/gymbox/pipeline/rep.py` — THE FIRST MILESTONE.** Implement the
   Python reference interpreter (`interpret(spec, stream)`):
   extrema-pair rep detection, dynamic position bands locked from the first rep,
   per-frame phase labeling via the provided `evaluate_phase`, segment
   coalescing. **Gate A:** against `tests/fixtures/bicep_curl_1.json`,
   rep-count error ≤ 1 and frame-phase agreement ≥ 85%. The test exists
   (`tests/test_gate_a.py`) and currently xfails; make it pass.
4. **gRPC server — SKIP for MVP-α.** (Edge-first; revisit at Phase 1+ for fixed
   cameras only. Do not build a streaming pipeline now.)
5. **Upload path hardening** — the FastAPI `/sessions` ingest is concrete;
   add the Postgres-gated ingest tests to CI (`GYMBOX_TEST_DB`).
6. **iOS client** — wire MediaPipe via the `PoseSource` protocol; record +
   upload (concrete pieces exist).
7. **`ios/.../DSLInterpreter.swift` — port the Python oracle.** **Gate B:** vs
   the Python output on the same fixture, ≥ 98% frame-phase identity, identical
   rep count, ±2-frame boundaries.
8. **`SessionRecorder.reinterpret()`** — once Gate B passes, generate live
   annotations on-device.
9. **Integration** — reference box round-trip: phone detects → uploads →
   Postgres → queryable back out.
10. **Reference Docker deployment** — `gymbox-box` (present; verify end-to-end).

**Gate A passes before Gate B.** A faithful port of a mistuned interpreter still
fails the product bar. If Gate A fails, the fix is almost always in
`exercises/db_curl.json` (thresholds, bands, smoothing), **not** the code.

---

## What NOT to do (these will get reverted)

- **Do not weaken the gates.** Never lower the 85% / 98% thresholds, the ±1 rep
  tolerance, or the ±2-frame boundary tolerance to make a test pass. If you
  can't hit the bar, retune the spec and write up why in `NOTES.md`.
- **Do not add a learned classifier on the runtime path in MVP-α.** No torch,
  no onnxruntime on the phone, in the ingest path, or inside the Python oracle.
  `model_spec` stays `null`. The interpreter is pure heuristic. (The offline
  *fitter* — `server/gymbox/fitter/`, dev-machine tooling — may use whatever
  optimization library it needs; that's not a runtime component.)
- **Do not change the DSL grammar to force a pass.** The phase eval order
  (RESET → ISO_LOADED → ISO_UNLOADED → CON → ECC, RESET first, first-match-wins)
  is locked. The signal/smoothing/rep primitives are locked.
- **Do not build gRPC, a streaming pipeline, a SessionRouter, or WebSockets.**
  Out of scope for MVP-α (architecture.md §14).
- **Do not down-cast the persistence schema to SQLite** to make tests run. The
  ORM uses Postgres-native JSONB/UUID and the `gymbox` schema on purpose. Ingest
  tests are Postgres-gated via `GYMBOX_TEST_DB`; keep them that way.
- **Do not make corrections bind by positional index.** They bind to
  `client_annotation_id` (architecture.md §8). Same for the two dedupe layers:
  `Idempotency-Key` = transport retry; `client_session_id` = durable session
  identity (re-upload = update, blob immutable).
- **Do not let the Swift keypoint registry drift from Python.** `Keypoints.swift`
  and `gymbox/dsl/keypoints.py` must stay byte-for-byte aligned, or Gate B is
  meaningless.
- **Do not commit generated protobuf code or secrets.** See `.gitignore`.

---

## Conventions

- Python ≥ 3.11, async throughout, type hints, Pydantic v2, SQLAlchemy 2.x.
- Swift 5.9, iOS 16+, no UI, minimal deps (URLSession only for networking).
- Every stub raises `NotImplementedError` (Python) / `fatalError` (Swift) with a
  ROADMAP pointer — don't leave silent no-ops.
- Tests: `cd server && pip install -e ".[dev]" && pytest`. The synthetic fixture
  is generated by `python scripts/make_fixture.py`; replace it with a real
  human-labelled capture when one exists (same JSON shape).

When in doubt, prefer the smallest change that satisfies the gate, and record
open questions in `NOTES.md` rather than expanding scope.
