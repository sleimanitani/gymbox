# gymbox — ROADMAP

The build plan for MVP-α and beyond. Architecture is locked at v0.7
(`docs/architecture.md`). This is edge-first: the phone infers, the server
stores + serves specs. Steps are ordered; each has an explicit acceptance bar.

Legend: ✅ done in this scaffold · 🔨 the work · ⏭️ deferred past MVP-α

---

## MVP-α — `db_curl` only, heuristic DSL, end-to-end

### Step 1 — Proto bindings 🔨
Generate Python + Swift bindings from `gymbox-proto/proto/gymbox.proto`.
- `cd gymbox-proto && ./scripts/gen_python.sh && ./scripts/gen_swift.sh`
- **Accept:** both packages build; the upload envelope round-trips a sample
  `SessionUpload` in Python and Swift. No gRPC service is generated.

### Step 2 — Core libraries ✅
DSL Pydantic models, keypoint registry, SQLAlchemy schema, FastAPI router, the
signal front-end, the materializer, and the reference-box factory are concrete.
- **Accept:** `pytest` green except the Gate A xfails; `db_curl.json` loads and
  round-trips; ETag is deterministic.

### Step 3 — Reference rep pipeline (`pipeline/rep.py`) — **FIRST MILESTONE** 🔨
Implement `interpret(spec, stream)`:
1. Extrema detection on the smoothed signal; pair into reps per `spec.rep`
   (`extrema_pair`, `min_amplitude`, `min_separation_s`, `prominence_frac`,
   `cycle_from`).
2. Lock dynamic position bands from the **first completed rep**'s min/max.
3. Per-frame phase via the provided `evaluate_phase` (first-match-wins, RESET
   first). Build `FrameContext` (velocity, direction, band, sign-change recency).
4. Coalesce frame phases into `PhaseSegment`s; assemble `InterpretResult`.
- The signal/smoothing/velocity front-end and `evaluate_phase` are **provided**.
- **Gate A (acceptance):** on `tests/fixtures/bicep_curl_1.json`, rep-count
  error ≤ 1 **and** frame-phase agreement ≥ 85% (`tests/test_gate_a.py`).
- **If it fails:** retune `exercises/db_curl.json` first. Do not touch the
  grammar or the thresholds.

### Step 4 — gRPC server ⏭️
**Skipped in MVP-α.** Edge-first means no real-time server inference. The proto
message types stay as the upload envelope only. gRPC + a streaming pipeline
return at Phase 1+ for fixed cameras — as a new module, undoing nothing here.

### Step 5 — Upload path hardening 🔨
The `/sessions` ingest is concrete (dual dedupe, immutable blob, last-write-wins,
corrections by `client_annotation_id`). Stand up a Postgres test DB and wire the
ingest tests into CI.
- `export GYMBOX_TEST_DB=postgresql+asyncpg://gymbox:gymbox@localhost/gymbox_test`
- **Accept:** `tests/test_ingest.py` passes; a re-upload updates annotations and
  leaves the skeleton blob unchanged; a repeated `Idempotency-Key` returns the
  cached result without reprocessing.

### Step 6 — iOS client 🔨
Wrap MediaPipe Pose Lite in a `PoseSource` (host-app binary dep). Wire
`SessionRecorder` (buffer frames), `ExerciseCatalog` (OTA + ETag),
`Uploader` (multipart + Idempotency-Key). The non-interpreter pieces are
concrete.
- **Accept:** a recorded `ReplayPoseSource` session uploads to the reference box
  and is queryable; the catalog 304s on an unchanged spec.

### Step 7 — Swift `DSLInterpreter` port 🔨
Port `pipeline/rep.py` to `DSLInterpreter.interpret`. The Swift signal
front-end (`Signal.swift`) and `evaluatePhase` are **provided**.
- **Gate B (port regression):** vs the Python oracle's output on the same
  fixture, ≥ 98% frame-phase identity, identical rep count, rep boundaries within
  ±2 frames.
- Gate A must already pass — the Python oracle is the ground truth here.

### Step 8 — On-device live annotation 🔨
Implement `SessionRecorder.reinterpret()` to run the ported interpreter and emit
`rep` / `rep_phase` annotations live, preserving stable
`client_annotation_id`s across re-interpretation.
- **Accept:** live events match the post-hoc interpretation; user corrections
  survive re-interpretation.

### Step 9 — Integration 🔨
End-to-end: phone detects reps/phases → uploads on Wi-Fi → Postgres → query API
returns materialized sets/reps.
- **Accept:** "MVP-α done" — phone detects, Python oracle agrees on the fixture,
  and a real session round-trips into Postgres and back out.

### Step 10 — Reference deployment ✅/🔨
`gymbox-box` (Compose: Postgres + app + nginx) exists. Verify the full
round-trip against it.
- **Accept:** `docker compose up` → `/ml/health` ok → seed/fetch a spec → upload
  a session → read it back.

---

## MVP-β — 3–4 dumbbell exercises, small classifier heads ⏭️
Shoulder press, lateral raise, one-arm row, goblet squat. Introduce per-exercise
`model_spec` (now non-null) feeding the interpreter as an extra signal. Decide
where training runs (Q16). Train off-box; push models via the model endpoint.

## Phase 1+ ⏭️
Cable + machine vocabulary, in-gym body ReID (server-side, pgvector schema
already present), card-tap kiosk, and — only here — fixed cameras with the gRPC
streaming path added back as a new module.

---

## Fixtures

`tests/fixtures/bicep_curl_1.json` is currently a **synthetic** stand-in
(`scripts/make_fixture.py`) so the harness and Gate A wiring are exercisable
today. Replace it with a real human-labelled capture (same shape:
`frames[].keypoints` = 33×[x,y,vis], `labels.rep_count`, `labels.frame_phases`)
as soon as one exists — the gates only mean something against real labels.
