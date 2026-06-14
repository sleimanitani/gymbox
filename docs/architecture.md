# gymbox — Architecture

**Status:** v0.7 (locked for MVP-α)
**Audience:** internal engineering + Claude Code as builder

**Key locked decisions (summary):**
- **Edge-first inference.** All real-time inference runs on the phone; the server is storage + a `/exercises` OTA spec channel + (future) training. No gRPC service and no streaming pipeline in MVP-α — proto message types are retained only as the upload-envelope schema.
- **Heuristic DSL detector for MVP-α.** `db_curl` only. The locked D6 grammar (JSON `rep_spec`/`phase_spec` in JSONB, `joint_axis` signal, Savitzky-Golay smoothing, `extrema_pair` rep detection with dynamic position bands, first-match-wins phases with RESET first) and the 13-layer annotation model are the source of truth.
- **Two-gate validation.** Gate A (Python reference vs. human labels — rep error ≤1, phase agreement ≥85%) is the acceptance bar; Gate B (Swift vs. Python — ≥98% phase identity, ±2-frame boundaries) is the port-regression bar. Gate A passes first (§4, §10).
- **On-device smoothing introduces latency.** The Savitzky-Golay filter emits reps after a half-window delay (~200–270 ms), not instantaneously — still far below a server round-trip (§3, §4).
- **Idempotency is two-layered.** `client_session_id` is durable session identity (re-upload = update, blob immutable); the `Idempotency-Key` header dedupes a single upload's network retries (§8).
- **Corrections reference stable IDs.** `user_corrections` bind to `client_annotation_id`, never positional index (§8).
- **Upload path is in MVP-α.** The full phone→server round-trip into Postgres is in scope; only *training* on collected data is deferred (§3, §14).
- **Three forward-compatibility reservations.** Proto field-number reservation for future signal carriers, an optional `model_spec` field on `ExerciseSpec`, and a documented signal-type vocabulary (§11).
- **Opaque bearer-token auth.** An `auth_validator` callback maps tokens to user IDs; the host app is the source of truth; the reference box ships Argon2id-hashed tokens (§12).

---

## 1. Goals & Non-Goals

### Goals (MVP-α)

- Track dumbbell bicep curl reps and rep-phases (CON / ECC / ISO / RESET) on an iPhone, with the phone as both camera and inference device.
- Persist a complete, multi-level annotation record per session to a server the integrator operates.
- Make adding new exercises a data operation, not a code operation: JSON spec + (optionally) one small model file.
- **Fit the JSON spec offline from labeled videos.** The thresholds, bands, and smoothing parameters in `db_curl.json` are not hand-guessed — they are produced by an offline *fitter* (dev-machine tooling) that searches the locked DSL grammar to maximize the Gate-A score against human labels, then a human audits the result before OTA. This is the (offline) ML in MVP-α (§10). It is distinct from the learned per-exercise `model_spec` classifier head, which is deferred (§11.2).
- Establish the data collection pipeline so that, when there's enough data to bother, training improved per-exercise models is straightforward and the rollout path to phones already exists.

### Non-Goals (MVP-α)

- *Learned-model* training infrastructure. Skeleton data is collected and stored; training a per-exercise classifier head (`model_spec`, §11.2) is deferred until there's a useful corpus. (Note: this is *not* the offline DSL spec **fitter** — that is in MVP-α scope and is how `db_curl.json` is produced; see §10.)
- Real-time server inference. The server is dumb storage in MVP-α.
- Body re-identification across cameras. Phase 1+.
- Multi-camera fusion. Phase 2+.
- A direct-to-consumer product. gymbox is a B2B library licensed to integrators; they own the UX.

### Staged delivery

**MVP-α is end-to-end, not detector-only.** It includes the full phone→server upload path: the SDK buffers a session locally, uploads it as a `POST /sessions` over Wi-Fi, and the `gymbox` FastAPI router validates, persists annotations, and stores the skeleton blob. What's deferred is *training* on that stored data (§5), not the *collection* of it. "MVP-α done" means: phone detects reps and phases, Python oracle agrees on the fixture, and a real session round-trips into Postgres and is queryable back out. (The offline `pipeline/rep.py` fixture validation is the *first* milestone within MVP-α — ROADMAP Step 3 — not the whole of it.)

| Stage | Scope | Where intelligence lives | Time from decisions lock |
|---|---|---|---|
| **MVP-α** | `db_curl` only, heuristic rep+phase detector via DSL interpreter | Phone (iOS) | 1–2 weeks |
| **MVP-β** | 3–4 dumbbell exercises, small per-exercise classifier heads | Phone (iOS) | +2–3 weeks |
| **Phase 1** | Cable + machine vocabulary, in-gym body ReID (server), card-tap kiosk | Phone + server | +6–8 weeks |
| **Phase 2** | Multi-camera fusion, federated training | Phone + server + edge box | TBD |

---

## 2. What We Ship

Three packages, deployable independently, integration-ready:

| Package | Form | What it is |
|---|---|---|
| **`GymboxSDK`** | Swift Package, iOS 16+ | Camera-attached SDK. Skeleton extraction (MediaPipe Pose Lite), DSL interpreter, session recording, upload-on-Wi-Fi. Zero UI. |
| **`gymbox`** | Python package | Server-side library. REST API, Postgres persistence, `/exercises` OTA spec channel, batch replay tools, reference DSL interpreter (golden oracle for the Swift port). |
| **`gymbox-proto`** | Protocol Buffers + Swift bindings + Python bindings | Shared message types. Defines the upload envelope. No gRPC service in MVP-α. |

A fourth artifact, **`gymbox-box`** (a reference Docker deployment of `gymbox` + Postgres), exists for demos and as a handoff template — not for production.

The integrator's host application owns: authentication, accounts, billing, UI, workout planning, business logic, payment, notifications, social features. gymbox owns: vision, rep/phase detection, annotation persistence, exercise spec lifecycle.

---

## 3. Edge-First Inference

The single most important architectural decision: **all real-time inference runs on the phone.** The server does not see frames in flight.

### Why

- UX latency floor is on-device latency, not network round-trip. "Rep 3 detected" appears within a fraction of a second of the rep — bounded by the Savitzky-Golay lookahead (half the smoothing window; see §4), not by a 200–800 ms round-trip on flaky gym Wi-Fi.
- Privacy story is dramatically simpler. Skeleton data, by default, does not leave the device until the user is back on Wi-Fi and charging. The user can opt out of upload entirely and the in-app experience is unaffected.
- The server scope drops by ~40%. No streaming pipeline, no SessionRouter, no real-time orchestration. Server becomes: REST + Postgres + `/exercises` + (future) training jobs.
- The DSL is a small JSON document and the interpreter is ~500 LOC of Swift. There's no ML-runtime dependency on the phone for MVP-α — MediaPipe Pose Lite is already running for skeleton extraction; running the DSL interpreter on the same stream adds negligible cost.
- Per-exercise models, when they exist, are tiny (sub-MB, INT8). Pushing them to the phone is cheap and the phone is already the inference target.

### What the phone does

The Swift SDK, given an `AVCaptureSession` and a bearer token:
1. Runs MediaPipe Pose Lite at ~15 Hz on the camera stream. Skeleton stays on-device.
2. Loads the user-selected exercise's `ExerciseSpec` (cached locally, refreshed from `/exercises` on launch and on user-initiated pull).
3. Interprets the spec to detect reps and rep-phases. Emits events to the host app via `AsyncStream<AnnotationEvent>`.
4. Buffers the session in a local SQLite database: skeleton frames (compressed), annotations, user actions, device metadata.
5. On Wi-Fi + non-cellular + (optionally) charging, uploads the buffered session as a single POST to `/sessions`. Sessions can age out locally per the integrator's retention policy.

### What the server does

The Python library, embedded in the integrator's backend:
1. Accepts session uploads at `POST /sessions`. Validates the schema, stores skeleton blobs and annotation rows.
2. Serves `GET /exercises` and `GET /exercises/{id}` — the OTA channel for DSL specs and (later) per-exercise models. Phones cache; server controls invalidation via ETag.
3. Provides query endpoints for the integrator's app to read sessions, sets, reps, summaries.
4. (Future) Runs batch jobs over collected sessions: produce labeled clips, retrain thresholds, train classifier heads. Updated specs/models flow back through `/exercises`.

### What this leaves out, deliberately

- No real-time correction signal from the server to the phone. If the phone is wrong about a rep count, it's wrong until the user fixes it in the UI; the user's correction is uploaded with the session and contributes to the training corpus.
- No federated learning, no on-device fine-tuning, no in-session adaptation. Specs are static between OTA refreshes.

---

## 4. iOS SDK (`GymboxSDK`)

**Form:** Swift Package, iOS 16+.

**Public surface (illustrative):**

```swift
public actor GymboxClient {
    public init(
        endpoint: URL,                       // integrator's gymbox server
        authToken: String,                   // bearer; SDK is token-opaque
        userId: String                       // integrator's user identifier
    )

    // Wire up to a camera session running elsewhere in the integrator's app.
    public func attach(_ session: AVCaptureSession) async throws

    // Start/stop a workout session. exercise_id is required in MVP-α.
    public func startSession(exerciseId: String, weightKg: Double?) async throws -> Session
    public func setExercise(_ exerciseId: String) async
    public func endSet() async
    public func endSession() async throws

    // Real-time events for UI.
    public var events: AsyncStream<AnnotationEvent> { get }

    // OTA spec refresh; idempotent; called at app launch.
    public func refreshExerciseCatalog() async throws

    // Upload control.
    public func uploadPolicy() -> UploadPolicy
    public func setUploadPolicy(_ policy: UploadPolicy)
}
```

**Internal modules:**

| Module | Responsibility |
|---|---|
| `PoseExtractor` | MediaPipe Pose Lite. Frame in, 33-keypoint skeleton + bounding box out, at ~15 Hz. |
| `DSLInterpreter` | Runs the locked DSL grammar against a streaming skeleton. Emits Rep, Rep Phase, Active, Inactive, Inactive Type, Set, Session, Movement Side events. **Port-regression gate:** must agree with the Python reference implementation on the `bicep_curl_1` fixture to a tight numeric tolerance — ≥98% frame-level phase identity, identical rep count, rep boundaries within ±2 frames. This is distinct from the acceptance gate (Python vs. human labels; see §10). Because the Savitzky-Golay filter needs lookahead, rep/phase events emit after a half-window delay (~200–270 ms at a 7–9 frame window @ 15 Hz), not on the instantaneous frame. |
| `SessionRecorder` | Local SQLite. Buffers skeleton (compressed via run-length on stationary frames), annotations, user actions. |
| `UploadManager` | URLSession background uploader. Wi-Fi + (optionally) charging gates. Resumable, idempotent. |
| `ExerciseCatalog` | Pulls `/exercises` on launch, caches with ETag, falls back to bundled. |

**Dependencies kept minimal:** MediaPipe Tasks (pose), SQLite.swift, no networking framework beyond URLSession. No combine, no SwiftUI dependencies (caller's choice).

---

## 5. Server Library (`gymbox` Python Package)

**Form:** Python ≥3.11, async throughout.

**Integration model:** The integrator's backend imports `gymbox` and mounts its FastAPI router under whatever prefix they like. They provide an `auth_validator` callback that maps bearer tokens to their user IDs. The library is otherwise self-contained: it owns its database tables under a schema prefix, runs Alembic migrations from its own migration tree, and exposes a Backend class with `start()` and `stop()`.

```python
from gymbox import Backend, Config

backend = Backend(Config(
    db_url="postgresql+asyncpg://...",
    auth_validator=my_app.auth.validate_token,
    exercises_dir="./exercises",
))
await backend.start()

# Mount the router into the host FastAPI/Starlette app.
app.include_router(backend.router, prefix="/ml")
```

**Modules:**

| Module | Responsibility |
|---|---|
| `gymbox.api.http` | FastAPI router: session upload, queries, OTA spec channel, admin endpoints. **The only API surface in MVP-α.** |
| `gymbox.persistence` | SQLAlchemy 2.x async ORM models, Alembic migrations. Schema in §9. |
| `gymbox.dsl` | Pydantic models for `ExerciseSpec` / `RepSpec` / `PhaseSpec`. Source of truth for the spec format. |
| `gymbox.pipeline.rep` | **Reference DSL interpreter in Python.** Used for: (a) golden-oracle testing of the Swift port; (b) batch replay of uploaded sessions during algorithm tuning; (c) labeling assistant during data labeling work. |
| `gymbox.pipeline.{activity,fsm,classifier,...}` | Reference implementations of the rest of the pipeline. Same role as `rep.py`: golden-oracle + batch replay. **Not on the runtime critical path.** |
| `gymbox.annotations.writer` | Bulk insert uploaded annotations into the polymorphic `annotations` table. |
| `gymbox.materializer` | Background job that denormalizes annotations into `sessions / sets / reps` for fast querying. Runs every few minutes; not real-time. |
| `gymbox.refdeploy` | Reference server entry point + default token validator. For `gymbox-box` and demos only. |

**What `gymbox` deliberately does not have in MVP-α:**

- No gRPC service. The `gymbox-proto` package ships message types (the upload envelope schema) but no service definition. gRPC is reserved for the day we need real-time server-side processing — e.g. when fixed cameras land in Phase 1+.
- No streaming pipeline. There is no `SessionRouter` or per-track ring buffer on the runtime path; sessions arrive as completed uploads, not live streams.
- No training jobs. Schema and storage are set up so collected data is trainable; the actual training scripts come when there's data to train on.

---

## 6. Identity & Cross-Camera Tracking (Phase 1+)

MVP-α does not need this — the phone is the user, the bearer token identifies the user, no further identity work is required.

Phase 1+ introduces fixed cameras in gyms. The architecture for that work:

- Card-tap kiosks at gym entry: associate `user_id` with a transient `visit_id` good for ~4 hours.
- CLIP-ReID embeddings stored in `body_embeddings` (pgvector, HNSW index, schema already in place).
- Temporal-consistency policy: a track keeps its assigned user_id unless ReID confidence diverges sharply for ≥3 consecutive seconds.
- Two-stage matching: visit-scoped gallery first (high precision), then enrollment gallery as fallback.

The `body_embeddings` table and `users.token_hash` field already exist in the schema; nothing in MVP-α blocks Phase 1+ ReID work.

---

## 7. Data Flow

### Upload happy path (MVP-α)

```
┌───────────────────┐
│   iOS host app    │
│  (integrator's)   │
└─────────┬─────────┘
          │ AVCaptureSession
          ▼
┌───────────────────────────────────────────────┐
│              GymboxSDK (phone)                │
│  ┌────────────────┐  ┌──────────────────┐     │
│  │ PoseExtractor  │─▶│  DSLInterpreter  │─▶ events ──▶ host app UI
│  │ (MediaPipe)    │  └────────┬─────────┘     │
│  └────────────────┘           ▼               │
│                       SessionRecorder         │
│                       (local SQLite)          │
│                               │               │
│                               ▼ when on Wi-Fi
│                       UploadManager           │
└────────────────────────────────┼──────────────┘
                                 │ POST /ml/sessions
                                 │ (JSON envelope + compressed skeleton blob)
                                 ▼
                  ┌──────────────────────────────┐
                  │  Integrator's backend        │
                  │  ┌────────────────────────┐  │
                  │  │ gymbox FastAPI router  │  │
                  │  └──────────┬─────────────┘  │
                  │             ▼                │
                  │       Postgres               │
                  │   ─ annotations              │
                  │   ─ sessions/sets/reps       │
                  │   ─ skeleton blobs           │
                  └──────────────────────────────┘
```

### Spec channel (`/exercises`)

```
Phone, on app launch and on user pull-to-refresh:
   GET /ml/exercises          → list with ETags
   GET /ml/exercises/{id}     → ExerciseSpec JSON + optional model file URL

Phone caches locally. ETag-driven. Falls back to bundled spec if offline.

Server, on spec update (admin endpoint):
   PUT /ml/admin/exercises/{id}  with new JSON (+ optional model file upload)

Phones pick up the change on next launch.
```

### Future data flow (Phase 1+, illustrative)

When fixed cameras land, the gRPC streaming path returns — but only for fixed cameras, not for phones. Phones remain edge-first. The server-side streaming pipeline (SessionRouter etc.) is added back at that point as a new module; nothing in the MVP-α architecture has to be undone.

---

## 8. APIs

### HTTP (the primary, only surface in MVP-α)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Upload a completed session. Body: JSON envelope + multipart skeleton blob. **Two distinct dedupe layers:** the envelope's `client_session_id` is the durable session identity (a re-upload of the same `client_session_id` with a revised annotation set is an *update* — last-write-wins on annotations, skeleton blob immutable once stored); the `Idempotency-Key` header dedupes transport-level retries of a single upload attempt (same key → server returns the prior result without reprocessing). See note below. |
| `GET` | `/sessions/{id}` | Retrieve session metadata + materialized sets/reps. |
| `GET` | `/users/me/sessions` | List user's sessions (paginated). |
| `GET` | `/sessions/{id}/annotations` | Full annotation list for a session. |
| `GET` | `/exercises` | List of available exercises with ETags. |
| `GET` | `/exercises/{id}` | One `ExerciseSpec`, with optional `model_url` for the per-exercise model file. |
| `GET` | `/health` | Liveness. |
| `POST` | `/admin/exercises` | Create/update exercise spec. Admin role required. |
| `POST` | `/admin/exercises/{id}/model` | Upload a model file for an exercise. Admin role required. |

WebSocket `/ws/sessions/{id}` is **deferred**. The integrator's app gets real-time events directly from the SDK on the phone, not from the server.

### Upload envelope schema

The body of `POST /sessions` is JSON described by message types in `gymbox-proto`:

```json
{
  "session": {
    "client_session_id": "uuid generated on phone",
    "user_id": "...",
    "started_at_utc": "...",
    "ended_at_utc": "...",
    "device": { "model": "iPhone 14 Pro", "ios_version": "17.4", "sdk_version": "0.1.0" },
    "exercise_id": "db_curl",
    "weight_kg": 14.0
  },
  "annotations": [
    { "client_annotation_id": "a3f1...", "layer_id": "rep_phase",
      "start_s": 2.972, "end_s": 3.704, "value": "CON",
      "source": "inference", "confidence": 0.92 },
    ...
  ],
  "user_corrections": [
    { "client_annotation_id": "a7c9...", "layer_id": "rep", "action": "delete",
      "reason": "false_positive" }
  ],
  "skeleton_blob": { "format": "gymbox-v1-skeleton", "url": "multipart-part-name" }
}
```

The `skeleton_blob` is the compressed pose stream (uploaded as a separate multipart part). The server stores it as-is for future training.

Each annotation carries a `client_annotation_id` — a stable identifier assigned on the phone at the moment the annotation is created. `user_corrections` reference annotations by this ID, never by positional index, so server-side reordering, filtering, or partial-insert never misbinds a correction to the wrong annotation. The server persists `client_annotation_id` alongside each row; corrections are resolved against it at insert time.

### Auth

`Authorization: Bearer <token>` on every request. The library calls `Config.auth_validator(token) -> user_id | None`. The host backend's auth system is the source of truth; gymbox is opaque to token internals.

### Idempotency & re-upload semantics

The two mechanisms answer different questions:

- **`Idempotency-Key` (HTTP header)** — "is this the same *upload attempt* I already processed?" Scope: a single POST and its network retries. The server caches the response keyed by this value for a short window; a retry returns the cached result without re-running the annotation writer. Protects against double-processing on flaky connections.
- **`client_session_id` (envelope field)** — "is this the same *workout session*?" Scope: the lifetime of that session's record. A second POST bearing a `client_session_id` the server has already stored is treated as an **update to that session**: annotations and `user_corrections` are re-applied last-write-wins; session metadata is updated; the `skeleton_blob` is immutable once first stored (a re-upload does not replace the blob). This is the path for "phone uploaded, user then corrected reps locally, phone re-uploaded the revised session."

The common case — one session, one upload, one network round-trip — exercises both: a fresh `client_session_id` and a fresh `Idempotency-Key`. They only diverge under retry (same key, same session) or local edit + re-upload (new key, same session).

---

## 9. Data Model

Schema lives in the `gymbox.persistence.models` module. Tables:

| Table | Purpose | MVP-α |
|---|---|---|
| `users` | Mirror of integrator's user identities. Created on first upload. | ✓ |
| `cameras` | Devices that produced data. In MVP-α: one row per phone. Forward-compat for fixed cameras. | ✓ |
| `exercises` | DSL specs. `rep_spec` and `phase_spec` are JSONB columns. | ✓ |
| `exercise_models` | (NEW) Optional per-exercise model file references. `exercise_id` FK, `version`, `sha256`, `storage_url`, `pushed_at`. Empty in MVP-α; populated when MVP-β classifier heads are trained. | ✓ schema only |
| `sessions` | One row per uploaded workout session. | ✓ |
| `sets` | Materialized from annotations. One row per set. | ✓ |
| `reps` | Materialized from annotations. One row per rep. | ✓ |
| `annotation_layers` | The 13 layer definitions (capture / session / exercise / equipment / weight / movement_side / set / active / inactive / inactive_type / rep / rep_phase / camera_angle). Seeded by migration. | ✓ |
| `annotations` | Polymorphic source of truth. Columns: `session_id` or `clip_id` (XOR), `layer_id`, `start_s`, `end_s`, `value`, `source`, `confidence`, `metadata`. | ✓ |
| `skeleton_blobs` | Uploaded compressed pose streams, stored in S3-compatible object storage (or local FS for the reference box). One row per session. | ✓ |
| `labeled_clips` | Human-labeled clips for offline training. Populated when labeling work begins. | ✓ schema only |
| `body_embeddings` | pgvector(512), HNSW index, cosine. Empty in MVP-α; Phase 1+ ReID populates. | ✓ schema only |

The phone produces the 13 annotation layers, the server stores them; the materializer derives the denormalized `sessions / sets / reps` rows asynchronously.

---

## 10. Exercise DSL: `rep_spec` & `phase_spec`

The locked `db_curl` spec in `server/exercises/db_curl.json` is the canonical reference for the grammar. An optional `model_spec` field is reserved at the `ExerciseSpec` level for future per-exercise models — see §11.

### Recap of the grammar

| Layer | Primitives |
|---|---|
| Signal source | `joint_axis` (MVP-α). Others reserved (§11). |
| Smoothing | `savitzky_golay` (MVP-α default), `gaussian`, `none`. |
| Rep detection | `extrema_pair` (MVP-α default), `velocity_zero_crossing` reserved. |
| Phase rules | `abs_v_lt/gt`, `direction: toward_high/toward_low`, `sign_changed_within_ms`, `position_band: low/mid/high` with dynamic bounds. |

Phase labels (first-match-wins, order matters): `RESET → ISO_LOADED → ISO_UNLOADED → CON → ECC`.

**Phase convention — fitted to labelled data (2026-06-14).** The operative
`db_curl` phase mapping is set by the offline fitter against the human-labelled
videos (see `docs/TRACKER.md` "Real-data findings") and follows the labellers'
convention, which is **signal/position-defined**, not muscle-tension-defined:

- **`ISO_UNLOADED`** — the *bottom/extended* hold: wrist low, signal in the LOW
  band, near-zero velocity.
- **`RESET`** — the *top/flexed* pause (signal HIGH band, near-zero velocity) and
  any other non-moving frame (the default label).
- **`CON`** — moving toward the high end (lifting). **`ECC`** — moving toward the
  low end (lowering).
- **`ISO_LOADED`** — *unused* by `db_curl` in MVP-α (the dataset effectively uses
  a single iso hold). The label stays in the grammar for other exercises.

This **supersedes the earlier muscle-tension framing** (which placed
`ISO_UNLOADED` at the top) for `db_curl`: per owner decision the standard follows
the data. The first-match-wins evaluation **order** above is unchanged and
remains locked; only the spec's rule *values* changed (the sanctioned offline-fit
mechanism — § offline spec fitting).

### Validation contract — two ordered gates

A spec's correctness and a port's fidelity are tested separately, in order, because they fail for different reasons and demand different fixes:

1. **Gate A — acceptance (Python reference vs. human labels).** The Python `pipeline.rep` interpreter is run against the human-labelled `bicep_curl_1` fixture. Bar: **rep-count error ≤ 1, frame-level phase agreement ≥ 85%.** A failure here is a *spec/tuning* problem — the thresholds, bands, or smoothing in `db_curl.json` are wrong. This is the real MVP-α acceptance criterion and must pass *first*; a faithful port of an interpreter that itself scores 82% still fails the product bar.
2. **Gate B — port regression (Swift vs. Python).** The Swift `DSLInterpreter` is run against the same fixture and compared to the Python output (not to the human labels). Bar: **≥ 98% frame-level phase identity, identical rep count, rep boundaries within ±2 frames.** A failure here is a *port* bug — S-G coefficients, an off-by-one in the extrema comparison, a boundary-index shift. Keeping Gate B's target tighter than Gate A's is deliberate: it isolates "the port drifted" from "the spec is mistuned" instead of collapsing both into one ambiguous number.

The Python reference is the golden oracle for Gate B precisely *because* it has already cleared Gate A. The ±2-frame rep-boundary tolerance absorbs legitimate cross-language divergence at the S-G window edges (see §4) without masking real logic differences.

### Storage and OTA delivery

Specs live as JSONB rows in the `exercises` table. The `GET /exercises/{id}` endpoint serves them with ETag for cache validation. Phones cache; falls back to bundled spec offline. Admin endpoint pushes updates.

### Adding a new exercise

1. Write `exercises/<id>.json`.
2. Validate by loading via `ExerciseSpec(...)`.
3. Push via admin endpoint.
4. (Optional, MVP-β+) Train a classifier head off-box on labeled clips; push the model file via the model endpoint; reference it from the spec's `model_spec` field.
5. Phones pick up the new exercise on next launch.

No code changes required on phone or server.

### Offline spec fitting — where the parameters come from

The values inside a spec (smoothing window/polyorder, `extrema_pair` amplitude /
separation / prominence, phase `abs_v` thresholds, position-band fractions) are
**fitted offline from labeled videos**, not hand-tuned. This is the (offline) ML
of MVP-α. The flow:

```
labeled videos ──► offline fitter ──► exercise spec JSON ──► human audit ──► OTA
  (skeleton JSON     (parameter search    (e.g.               (sanity-check       (phones pick
   + ground-truth     over the LOCKED      db_curl.json)       on held-out         up the spec
   phase + rep        DSL grammar;                             clips)              on next
   labels/frame)      objective = max                                              launch)
                      Gate-A score)
```

Properties that keep this inside the architecture's guarantees:

- **Dev-machine tooling, not a runtime component.** The fitter runs offline; it
  is never in the phone path, the ingest path, or the Python oracle. Its output
  is a JSON spec — a heuristic specification, not a learned model. The runtime
  stays pure heuristic (§3).
- **It optimizes Gate A.** The objective is the Python interpreter's score vs.
  human labels on the held-out fixture (Gate A above). The fitter does not pass
  unless the spec it produces would.
- **It does not invent grammar.** The DSL grammar is locked (§10 recap); the
  fitter only chooses values *within* it. A new primitive is an architecture
  change, not a fitter output.
- **Distinct from `model_spec`.** This produces the heuristic spec. The learned
  per-exercise classifier head (§11.2) is a separate, later concept (MVP-β+);
  the two never conflate.
- **Where it will live:** `server/gymbox/fitter/` (planned; not in the initial
  commit). Inputs: paired skeleton + label JSON. Output: an `ExerciseSpec`-
  compatible JSON dict. May use any optimization library it needs — it is not a
  runtime dependency.

---

## 11. Forward Compatibility — the Three Reservations

These exist to ensure that future capabilities slot in without breaking changes. They cost nothing today and protect a lot of optionality.

### 11.1 Proto field-number reservation

Field numbers in `PoseFrame` (and `ClientMessage`, `ServerMessage` when they exist) are **reserved** for future signal carriers. Specifically, in `PoseFrame`:

```proto
message PoseFrame {
  // ... existing fields 1-8 (see the PoseFrame definition in §7) ...

  // RESERVED for future signal carriers. Do not assign without bumping
  // proto package version.
  reserved 9 to 15;
  reserved "hand_landmarks", "objects", "device_orientation",
           "imu_window", "audio_features", "user_intent_hint", "scene_label";
}
```

The named placeholders signal intent for documentation; the field numbers themselves are what's protected. Proto3 makes reused field numbers extraordinarily dangerous (silent data corruption); reserving them now is the cheapest possible insurance.

### 11.2 `model_spec` reservation on `ExerciseSpec`

The `ExerciseSpec` Pydantic model gains an optional `model_spec` field, null in MVP-α:

```python
class ModelSpec(BaseModel):
    """Optional per-exercise model attached to a DSL spec. Null in MVP-α."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["onnx_classifier_head"]   # extensible later
    storage_url: str                        # /exercises/{id}/model or external
    version: str                            # semver
    sha256: str                             # integrity check
    input_window_frames: int = 32
    input_stride_frames: int = 8
    confidence_threshold: float = 0.5

class ExerciseSpec(BaseModel):
    # ... existing fields ...
    model_spec: ModelSpec | None = None
```

When `model_spec` is null, the DSL interpreter is the sole detector. When it's populated, the interpreter feeds frames through the model and uses model output (per the kind's contract) as an additional signal. The MVP-α phone code path checks `if model_spec is not None` and treats null as a no-op — no model loading, no runtime overhead.

This means **shipping per-exercise models in the future does not require changing the spec schema version, the API, the proto, or the DB schema.** It's an additive change that all the existing infrastructure transparently handles.

### 11.3 Documented signal-type vocabulary

The DSL's `signal.type` is a discriminated union. Adding a new type is non-breaking; what we lock in now is the *intended* vocabulary so anyone extending the DSL knows the lane:

| Signal type | Status | Use case |
|---|---|---|
| `joint_axis` | ✅ Implemented MVP-α | Curl, raise, press, row — one joint, one axis |
| `joint_angle` | 🔵 Reserved | Tricep extension, squat depth — angle at a vertex joint |
| `joint_distance` | 🔵 Reserved | Overhead press, deadlift — distance between two joints |
| `hand_landmark_axis` | 🔵 Reserved | Hammer curl vs reverse curl — wrist orientation |
| `object_keypoint` | 🔵 Reserved | Barbell endpoints, plate count — requires object detection |
| `imu_axis` | 🔵 Reserved | Wearable integration |
| `composite` | 🔵 Reserved | AND/OR/SEQ over multiple signals (e.g., rep counts iff knee angle < 90°) |

Phones running an older interpreter that encounters an unknown `signal.type` reject the spec at parse time and fall back to the bundled spec (graceful degradation). New exercises depending on a new signal type ship to phones running the corresponding interpreter version.

### What the three reservations together unlock

The two cases the user raised — and the harder versions of them — map cleanly:

- **Tricep rope pushdown vs biceps cable curl** (opposite trajectories): handled today via `cycle_from`. No reservation needed.
- **Hammer curl vs reverse curl** (identical skeleton, only wrist orientation differs): solved later via `hand_landmark_axis` (signal-vocabulary reservation) + proto `hand_landmarks` field (proto reservation). Adding it changes only the SDK's MediaPipe Tasks invocation, the proto's `PoseFrame`, and the DSL signal interpreter — all additive.
- **Form-gated rep counting** (a squat only counts if knee dipped below parallel): solved later via `composite` signal type. Additive.
- **Per-exercise learned classifier head** for ambiguous cases unsolvable by hand-tuned rules: solved later via `model_spec`. Additive.

None of these require revisiting the architecture, the schema, or the API. They each require code in the phone's interpreter and possibly a new value in an enum. The deployment unit remains "the exercise" — JSON + optionally model file.

---

## 12. Auth Contract (L1)

Opaque bearer tokens; iOS SDK passes them through; Python library accepts an `auth_validator: Callable[[str], Awaitable[str | None]]` callback. The reference box ships a `DefaultTokenValidator` (Argon2id-hashed tokens) for demos. Migration to JWT is non-breaking when needed.

---

## 13. Packaging, Integration, & Reference Deployment

### What an integrator does

1. **Add the SDK to their iOS app.** Swift Package via SPM. Configure with their server URL and the user's bearer token. Hook up to the AVCaptureSession they already have.
2. **Add the Python library to their backend.** `pip install gymbox`. Configure `db_url` and `auth_validator`. Mount the FastAPI router. Run Alembic migrations.
3. **Decide where skeleton blobs live.** S3, GCS, local FS — configured via `Config.blob_storage_url`. Default for the reference box is local FS under `./data/blobs`.

That's it. No daemons, no edge box, no GPU.

### Reference deployment (`gymbox-box`)

Docker Compose with Postgres + the Python library running behind nginx. Demo-grade. Useful for our own internal testing, for integrators evaluating the product, and for very small pilots (≤ 50 users).

Production deployments are the integrator's, on their cloud, behind their auth — not ours.

---

## 14. What's NOT in MVP-α (re-stated for clarity)

- Real-time server inference
- gRPC service (proto message types exist; no service definition)
- Streaming pipeline on the server (`SessionRouter`, real-time fanout)
- Body re-identification
- Multi-camera fusion
- *Learned-model* training pipeline (data is collected; training is deferred). The offline DSL spec **fitter** (§10) is *in* MVP-α — it is how `db_curl.json` is produced — and is not a runtime component.
- Per-exercise models (`model_spec` field exists and is null)
- Hand-landmark / object-detection signals (proto fields and signal types reserved)
- WebSocket real-time event feed from server
- Federated learning
- DP noise on uploads
- iOS UI components (SDK ships zero UI)
- Android (iOS only in MVP-α)
- More than one exercise (`db_curl` only in MVP-α)

---

## 15. Open Decisions

- **[Q3]** Body-embedding consent flow — deferred to Phase 1.
- **[Q4]** Federated upload DP noise spec — deferred to Phase 2.
- **[Q16]** Where MVP-β training runs — off-box dev machine vs per-gym. Decide before MVP-β.
- **[Q17]** Skeleton blob storage default — local FS for the reference box is fine; production-default (S3 vs GCS) is integrator's choice.
- **[Q18]** Spec OTA refresh cadence and stale-cache policy — current default: refresh on launch, no max-age beyond ETag. Revisit if integrators report stale-cache issues.

Nothing else is blocking. Architecture is locked at v0.7 for MVP-α; ready for implementation.
