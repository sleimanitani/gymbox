# gymbox — Product Overview

**A computer-vision library for gym exercise tracking, licensed to integrators who build apps and software for gyms.**

---

## What it is

gymbox is a B2B library that turns a phone camera into an exercise tracker. Point the phone at someone lifting and gymbox tells you what they did: which exercise, how many reps, how each rep was performed (concentric, eccentric, hold, transition), at what weight, on which side. The signal is rich enough to drive a workout app, a coaching tool, a gym-management dashboard, or a piece of connected equipment.

It is not a consumer product. There is no gymbox app, no gymbox brand on the phone, no gymbox login. Integrators embed gymbox in their own apps and software, under their own brand, on their own terms.

---

## Who it's for

| Buyer | What they get |
|---|---|
| Gym software companies building member-facing apps | A rep-counting and form-tracking layer they don't have to build |
| Whitelabel fitness app vendors | A differentiator that's hard to clone, deployable to existing iOS clients |
| Connected-equipment manufacturers | A camera-based tracking pipeline that complements (or replaces) embedded sensors |
| Personal training platforms | Programmatic access to a client's actual lifts, not what they self-reported |

The integrator owns the relationship with the gym. gymbox is an ingredient.

---

## What you get when you license gymbox

Three packages and the rights to ship them inside your product:

### 1. `GymboxSDK` (iOS, Swift Package)
The piece that runs on the user's phone. You attach it to a camera session your app is already running. It identifies the person doing the exercise, counts the reps, classifies the phase of each rep, and emits events as they happen. UI is yours — the SDK is camera-in, events-out. iOS 16+. ~3-5 MB compiled. No required background daemons. Battery cost: ~5-8% per hour of active tracking.

### 2. `gymbox` (Python, server library)
The piece that runs in your backend. You pip install it into your existing FastAPI / Starlette / async-Python stack. It owns its database tables, exposes a small HTTP API (under a prefix you control), and accepts session uploads from the SDK. Your backend continues to own users, authentication, billing, business logic, UI, notifications, and everything else. gymbox owns vision and rep detection.

### 3. `gymbox-proto`
The wire format that the SDK and server library speak. You don't interact with it directly; both packages depend on it. It's separately versioned so SDK and server can roll independently as long as the proto major version matches.

There's also an optional **reference Docker deployment** (`gymbox-box`) — Postgres + the Python library behind nginx, in compose. Useful for evaluation and demos. Not how you'd run this in production; you'd embed `gymbox` in your own backend.

---

## What you build

You build the rest of the application. Concretely:

| Yours | gymbox's |
|---|---|
| iOS app (UI, workout planning, social features, branding) | SDK runs inside it; emits events you display |
| Backend (accounts, auth, billing, user data, notifications) | Library runs inside it; exposes a few endpoints under your prefix |
| Database (users, subscriptions, gym contracts, payments) | Owns its own tables under a schema prefix; foreign-keys to your `users` |
| Authentication system (login, tokens, sessions) | Accepts your bearer tokens and asks your code to validate them |
| Camera permission, capture session, frame pipeline | Receives frames from your `AVCaptureSession` |
| Workout templates, exercise libraries, programs | Consumes the exercise IDs you assign to sets |
| Analytics, dashboards, reports | Reads data via the library's query API or directly from Postgres |

The integration model is: gymbox is a tenant in your application, not the other way around.

---

## Where the intelligence lives

**On the phone.** The phone runs MediaPipe Pose on the camera feed, interprets a small JSON specification of the current exercise, and tells your UI when something happened. The server is for storage, queries, and over-the-air updates to those specifications.

This means:
- Reps appear in your UI within a fraction of a second of happening, with no network round-trip — the only delay is the on-device signal smoothing, far below the lag of a server round-trip on gym Wi-Fi.
- Sessions work offline. Skeleton data buffers locally and uploads when the user is on Wi-Fi.
- Privacy is straightforward: skeleton data does not leave the device until the user is back on Wi-Fi, and your users can choose not to upload at all without losing the in-app experience.
- The server is dumb storage in MVP. It scales easily.

The "intelligence" is largely a few hundred lines of well-tuned heuristics encoded as JSON. As we collect labelled data through deployments, those JSON specs will be augmented with small per-exercise models, pushed to phones via the same mechanism. From the integrator's perspective, exercises just get more accurate over time without any code changes.

---

## How exercises get added

Adding a new exercise is a data operation, not a code release. Each exercise is one JSON file describing how to track it: which joint to watch, how to smooth the signal, how to count reps, how to identify phases. Optionally, a small machine-learning model file is attached for cases where heuristics aren't enough.

These specs live on the server and phones download them on launch. Adding "dumbbell shoulder press" to your app, after the relevant exercise is published in gymbox, is zero work on the integrator's side. The phone will see it on next refresh.

This is the property that determines whether gymbox is good as a product over time: every gym that uses it generates labelled data, every batch of labelled data improves the specs, every improved spec reaches every phone running gymbox. The system gets better as it gets used.

---

## What gymbox tracks (current and planned)

| Stage | Exercises | When |
|---|---|---|
| **MVP-α** | Dumbbell bicep curl | Day one |
| **MVP-β** | + Dumbbell shoulder press, lateral raise, one-arm row, goblet squat | + 2-3 weeks after MVP-α |
| **Phase 1** | + Cable + machine vocabulary (~15 exercises), in-gym body re-identification | + 6-8 weeks |
| **Phase 2** | Full dumbbell + cable + machine vocabulary (~40 exercises), multi-camera fusion | TBD based on pilot data |
| **Phase 3** | Barbell, kettlebell, bodyweight (push-ups, pull-ups, dips, squats) | Roadmap |

For each exercise, gymbox reports:
- **Active vs Inactive** time and type (idle, setup, between-set rest)
- **Sets** (start, end, exercise, weight, movement side: left / right / both / alternating)
- **Reps** (count, individual rep duration, amplitude)
- **Rep phases** (concentric, eccentric, isometric-loaded, isometric-unloaded, reset) — loaded vs. unloaded is defined by tension on the *target muscle*, not by whether weight is present: a curl held at the top is isometric-*unloaded* (biceps shortened, minimal tension), held at the bottom is isometric-*loaded* (biceps lengthened, resisting).
- **Camera angle** classification (front, three-quarter, side, back)

Down to the rep-phase level, all annotations are time-stamped and queryable. Your app can display "rep 4 of set 2 had a 0.7s concentric phase and a 1.4s eccentric phase, with 200ms hold at the top" if that level of detail matters to your product.

---

## Integration touchpoints

The full list of places where your code meets gymbox:

**On the phone (iOS):**
1. Add the Swift Package to your Xcode project.
2. Instantiate `GymboxClient(endpoint:, authToken:, userId:)`.
3. Call `attach(_:)` with your existing `AVCaptureSession`.
4. Start a session with `startSession(exerciseId:, weightKg:)` when the user begins a set.
5. Listen to `events` (`AsyncStream<AnnotationEvent>`) and update your UI.
6. Call `endSet()` between sets and `endSession()` when the user is done.

**In your backend (Python):**
1. `pip install gymbox`.
2. Provide an `auth_validator` callback that maps your bearer tokens to user IDs.
3. Configure the database URL.
4. Mount the FastAPI router under whatever prefix you like.
5. Run `alembic upgrade head` to create gymbox's tables.

**Operationally:**
- Choose where skeleton blob uploads land (S3, GCS, local FS).
- Decide your retention policy. Default: annotations forever, skeleton blobs 30 days.
- Decide your upload policy default (Wi-Fi only / Wi-Fi + cellular / charging-only).

That's the entire integration surface.

---

## Data ownership

Everything gymbox collects lives in **your** infrastructure. The library runs in your backend, writes to your Postgres, uploads to your object storage. There is no central gymbox cloud that aggregates user data across customers.

Specs and models flow the other direction: gymbox publishes them, your server caches them, phones pull them via your server. The OTA channel doesn't carry user data, only spec files.

This matters for:
- **GDPR / EU data residency**. Your data, your jurisdiction, your DPIA.
- **EU AI Act classification**. Skeleton data is currently not considered biometric for identification purposes under EU guidance (it's a pose abstraction, not a face/iris/fingerprint). gymbox is positioned as a limited-risk system; documentation supports this stance.
- **Pilot trust**. Gyms ask "where does our members' data go." The answer is "to your software vendor's cloud" — the same place all their other data goes.

A **labelled data sharing agreement** is something we'll offer separately: integrators who opt in to share anonymized skeleton clips for spec improvement get earlier access to new exercises and better-tuned specs. This is opt-in and contractual, not on-by-default.

---

## What gymbox does NOT do

Drawing the boundaries explicitly:

- **Not a workout app.** No UI, no programs, no calendar, no logging interface — that's the integrator's product.
- **Not a coaching engine.** Doesn't tell you "your form is wrong" or "you should increase the weight." It tells you what happened, accurately and at high resolution. Coaching is a layer the integrator builds on top.
- **Not nutrition, recovery, sleep, or wearable integration.** Out of scope.
- **Not a CRM, billing, or gym-management system.** Out of scope.
- **Not a face / person identifier.** In Phase 1+ it does in-gym body re-identification using clothes-and-shape embeddings, scoped to a single visit and gallery-bounded. Faces are never stored.
- **Not a video archive.** Skeleton data is uploaded; raw video stays on the phone, optionally as low-rate JPEG thumbnails (off by default).
- **Not a real-time multi-user system.** Each phone tracks one person. Multi-person fixed cameras are Phase 1+.

---

## Versioning and stability

| Surface | Stability commitment |
|---|---|
| iOS SDK public API | Stable within a major version. Breaking changes flagged a minor before, with a one-version migration window. |
| HTTP API endpoints | Stable within a major version. Forward-compatible additions (new endpoints, optional fields) at any time. |
| `gymbox-proto` major version | Bound to SDK major version. New fields are non-breaking; removed fields require a major bump. |
| DSL `ExerciseSpec` schema | Versioned via `schema_version` integer. Phones supporting an older `schema_version` ignore newer specs (graceful degradation). |
| Database schema | Forward-only migrations via Alembic, included in each release. |
| Exercise vocabulary | Additive — new exercises don't deprecate old ones. |

Semver throughout. Integrators receive a release notice and changelog per release.

---

## Roadmap from the integrator's perspective

| You get | When |
|---|---|
| Working bicep curl tracking, end-to-end, ready to demo | MVP-α (1–2 weeks from architecture lock) |
| 5 dumbbell exercises with classifier-backed accuracy | MVP-β (+2-3 weeks) |
| Cable + machine vocabulary, in-gym ReID, card-tap kiosk pattern | Phase 1 (+6-8 weeks; first paid pilot territory) |
| 40-exercise vocabulary, multi-camera fusion, on-edge box option | Phase 2 (timeline depends on pilot data) |
| Barbell + kettlebell + bodyweight | Phase 3 |

Each phase is independently deployable. The same SDK, library, and API surface carry through; new capabilities arrive as new exercise specs and (eventually) attached models, delivered via the OTA channel. You don't ship a new SDK to get more exercises.

---

## Pricing

Per-active-user-per-month or per-gym-license. Volume tiers. Contact for terms — pricing is per-integrator, scoped to the deployment size and exercise vocabulary.

---

## Why this and not something else

**vs. building it in-house.** Real-time pose-based exercise tracking is a 6-12 month engineering investment with continuous tuning work afterward. The vocabulary scales with effort: each new exercise needs labelling, threshold tuning, and validation. gymbox amortizes that across all integrators.

**vs. wearable / IMU-based tracking.** Wearables miss form. They count reps but can't tell concentric from eccentric, can't tell movement side, can't tell which exercise. Wearables also impose a hardware-adoption requirement on your users; gymbox runs on the phone they already have.

**vs. fixed-camera systems.** Fixed cameras require gym-side installation and a recurring hardware/maintenance cost. gymbox runs on the user's existing phone. Phase 1+ supports fixed cameras as an *addition* to phone tracking, not a replacement.

**vs. closed-system competitors** (Tonal, Tempo, Liteboxer, etc.). Those are vertically integrated hardware products. gymbox is a software ingredient you put inside *your* product.

---

## What we ask of integrators

- **Pilot data.** During the early phases, integrators help us collect labelled clips from their gyms. The opt-in is theirs and their users'; the data is bidirectional value (better specs faster).
- **Feedback on the wire formats.** SDK and HTTP API are versioned and stable, but the early integrators have outsized influence on what fields, endpoints, and event types we ship in v1.
- **Honest reporting on what works and what doesn't.** Computer vision is not magic; the product gets better the more we hear from the field.

---

*This document is the external-facing positioning of gymbox. For internal engineering detail, see ARCHITECTURE.md. For the build plan, see ROADMAP.md.*
