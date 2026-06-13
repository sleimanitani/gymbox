# gymbox — WORKLOG

**The single source of truth for "what are we doing right now and how far along."**
Survives across Claude Code sessions and crashes. Every session reads this first
and keeps it current.

> Scope split (don't duplicate):
> - **WORKLOG.md** (this file) — *active plans and their step-by-step progress*, plus the session index.
> - **TRACKER.md** — *component/gate status* (what's concrete vs stub) and Gate-A/B tuning experiments.
> - **NOTES.md** — open questions and judgment calls.

---

## Operating protocol (read before doing anything)

1. **Plan before action.** Before taking any action that changes files, runs a
   migration, commits, or pushes: add a **Plan** entry under "Active plans"
   below with its steps as checkboxes. No silent work.
2. **Update as you go.** Tick each step the moment it's done (`[ ]` → `[x]`).
   If a step is in progress, mark it `[~]` and add a one-line note. This is what
   makes a crash recoverable — the file always reflects reality on disk.
3. **One plan = one goal.** When all steps are `[x]`, move the whole entry to
   "Completed plans" with the finish date. Keep the steps for the audit trail.
4. **On crash / new session:** read this file top-to-bottom. Any `[~]` or
   unchecked step in an Active plan is where to resume. For deeper context on
   what a past session was thinking, open its transcript (see "Session index").
5. **Record decisions inline.** When the user makes a call (branch name, author,
   scope), write it into the relevant plan so it's never re-litigated.

---

## Active plans

_None. Next up: ROADMAP Step 10 — verify `gymbox-box` (Docker Compose:
Postgres + app + nginx) end-to-end: `docker compose up` -> `/ml/health` ->
seed/fetch a spec -> upload a session -> read it back. The latent layer-seed
gap that would have broken ingest is already fixed (`seed_reference_data`).
Note: Docker isn't available on this box, so Step 10 may need the user's env.
Open a plan here before starting._

---

## Completed plans

### Plan 2026-06-13-C — Integration round-trip (Step 9) — done 2026-06-13
**Goal:** prove "MVP-α done" — a detected session round-trips through ingest
into Postgres, materializes, and reads back as sets/reps.
**Session:** `0558415f-c661-422e-816d-4558654b95ae`.
**Result:** **DONE.** `tests/test_integration.py` (Postgres-gated): interpret ->
upload envelope (rep + rep_phase, as the phone sends) -> `ingest_session` ->
`materialize_pending` -> `read_session` returns 1 set with all 8 reps, each
carrying phase_durations. Full suite: 23 passed WITH Postgres; 18 passed / 5
skipped WITHOUT (clean gating).
**Fixes made along the way:**
- `Database.seed_reference_data()` added (idempotent annotation-layer seed) and
  wired into the reference-box startup — `create_all()` never seeded the layer
  FK rows, so ingest (and the Step-10 ref box) would have failed the layer FK.
- Repaired stale `test_ingest.py`: wrong read-API kwargs (`user_external_id` ->
  `user_id`), wrong id (client_session_id -> db uuid), dict access on
  `read_annotations`. They had never run (Postgres never configured); now green.
- Shared Postgres-gated `db` fixture moved to conftest (create_all + seed).
**Env note:** no Docker / no PG server on PATH, but PG 16 binaries at
`/usr/lib/postgresql/16/bin`. Verified against a throwaway cluster
(initdb -> pg_ctl on 127.0.0.1:5433, role+db gymbox/gymbox_test). See [[dev-env]].

- [x] **Provision local Postgres** — throwaway PG16 cluster; `GYMBOX_TEST_DB` set.
- [x] **Fix stale `test_ingest.py`** — now passes against real Postgres.
- [x] **Write `test_integration.py`** — round-trip asserts 8 reps + phase durations.
- [x] **Run full suite** — 23 passed (PG) / 18 passed + 5 skipped (no PG).
- [x] **Docs** — TRACKER rows + integration gate note; plan -> Completed;
      session index. Commit + push.

---

### Plan 2026-06-13-B — SessionRecorder.reinterpret() (Step 8) — done 2026-06-13
**Goal:** generate on-device rep/rep_phase annotations from the Gate-B interpreter.
**Session:** `0558415f-c661-422e-816d-4558654b95ae`.
**Result:** **DONE.** `reinterpret()` runs `DSLInterpreter.interpret` and emits
`rep` + `rep_phase` `LocalAnnotation`s with deterministic, ordinal-based
client_annotation_ids; user/non-inference annotations preserved. Standalone
swiftc verify on the fixture: 8 rep rows, 33 phase rows (values = phase labels),
idempotent across repeated calls (no growth, unique ids), a user correction
survives 2x re-interpretation. `swiftc -typecheck` clean. Two XCTests added.
**Design:** `rep_phase` value = phase label (materializer keys durations by it);
`rep` amplitude stays null in MVP-α (wire schema carries no metadata channel —
no schema expansion). ids are `String(64)` not UUIDs, so deterministic ids are
safe + idempotent (architecture.md §8).

- [x] **Implement `reinterpret()`** — rep + rep_phase rows, deterministic ids,
      corrections preserved.
- [x] **Standalone verify** — swiftc harness over SessionRecorder + Pose + DSL
      sources; all assertions PASS.
- [x] **Docs** — TRACKER row updated; plan moved to Completed; session index.
      Commit + push.

---

### Plan 2026-06-13-A — Port DSLInterpreter.swift (Gate B) — done 2026-06-13
**Goal:** port `DSLInterpreter.interpret` to match the Python oracle on
`bicep_curl_1` (>=98% identity, identical rep count, +/-2-frame boundaries).
ROADMAP Step 7.
**Session:** `0558415f-c661-422e-816d-4558654b95ae`.
**Result:** **Gate B PASS — exact parity.** 100% frame-phase identity, rep
count 8/8, 0-frame max boundary deviation. The Swift port reproduces the
Python oracle bit-for-bit.
**Env note:** installed Swift 6.3.2 via swiftly
(`~/.local/share/swiftly/toolchains/6.3.2/usr/bin/swiftc`). Full `swift test`
can't link here (SDK target's URLSession files need FoundationNetworking +
libcurl-dev, no sudo); verified by compiling the 5 DSL sources standalone
with `swiftc` against the golden oracle output. See [[dev-env]] note in memory.

- [x] **Golden oracle output** — `oracle_bicep_curl_1.json` generated from the
      Python oracle, bundled in `ios/Tests/GymboxSDKTests/Fixtures/`.
- [x] **Implement `DSLInterpreter.interpret`** — ported detection core +
      `alternatingExtrema` / `detectReps` / `msSinceSignChange` /
      `coalesceSegments`, faithful to rep.py.
- [x] **Standalone verify** — `swiftc` over the 5 DSL sources + a harness;
      Gate B PASS (100% / 8 / 0-frame). Sources `swiftc -typecheck` clean.
- [x] **Real Gate B XCTest** — replaced `testInterpreterPortIsPending` with
      `testGateB_matchesPythonOracle` (asserts the three Gate B bars).
- [x] **Docs** — TRACKER status + Gate B result + experiment; plan moved to
      Completed; session index updated. Commit + push.

---

### Plan 2026-06-10-A — Implement `pipeline/rep.py` interpret() (Gate A) — done 2026-06-10
**Goal:** implement the Python reference oracle's `interpret()` so Gate A passes
on `bicep_curl_1`. ROADMAP Step 3 / the first MVP-alpha milestone.
**Session:** `0558415f-c661-422e-816d-4558654b95ae`.
**Result:** **Gate A PASS** — rep error 0 (8/8), phase agreement 0.884 (floor
0.85). `db_curl.json` left unchanged. Full suite 18 passed / 3 Postgres-skipped
(3 Gate A tests flipped xfail->pass). Synthetic fixture -> proves plumbing, not
tuning (TRACKER.md / NOTES.md).
**Env note:** repo Python is 3.10 but pkg needs >=3.11 -> provisioned a
uv-managed 3.12 venv at `server/.venv` (gitignored). Run tests with
`server/.venv/bin/pytest`.

- [x] **Extrema detection** — pure-NumPy alternating-pivot (zig-zag) finder over
      the smoothed signal; delta = max(min_amplitude, prominence_frac x
      peak-to-peak); min-separation guard; closes the final pending pivot at
      stream end so the last rep isn't dropped.
- [x] **Rep detection** — pairs pivots into low->high->low cycles (cycle_from),
      amplitude-gated by min_amplitude, emits RepEvents.
- [x] **Dynamic bands** locked from the first completed rep (`fit_from_rep`),
      applied to all frames (offline oracle has full lookahead).
- [x] **Per-frame phase labeling** — FrameContext (abs_v, direction, band,
      sign-change recency) -> `evaluate_phase` -> `coalesce_segments` ->
      InterpretResult.
- [x] **Gate A run** — passes; experiment logged in TRACKER.md. No spec retune.
- [x] **Full suite green** + TRACKER status rows updated for `rep.interpret`
      and Gate A.

---

### Plan 2026-06-08-A — Doc reorientation + first commit — ✅ done 2026-06-09
**Goal:** make the offline ML fitter first-class in the docs, clarify the
interpreter, then make and push the first git commit.
**Origin session:** `dfe32566-721e-421d-95bc-d416644b027f` (crashed 11:40,
stream idle timeout). **Finished by:** `0558415f-c661-422e-816d-4558654b95ae`.
**Decisions (locked by user):** remote already exists → just push · cleanup =
docs only, no code · author `solomon <s@y76.io>` · default branch `main` ·
remote `git@github.com:sleimanitani/gymbox.git`.
**Result:** first commit `8b53a10` (79 files), pushed to `origin/main`.

- [x] **CLAUDE.md** — added "what interpreter/spec mean" + "offline spec fitting
      (where ML lives)" sections; recast "no ML" → "no *runtime* ML on
      phone/ingest/oracle; offline fitter is in scope". *(done by dfe32566; both
      edits verified on disk)*
- [x] **architecture.md** — §1 goal + non-goal reframed (offline fitter in
      MVP-α scope, learned `model_spec` deferred), new §10 "Offline spec fitting"
      subsection (labeled videos → fit → human audit → OTA), §14 clarified.
- [x] **README.md** — in-one-breath para + gates section mention the offline
      fitter; docs table + Claude pointer now mention WORKLOG.
- [x] **git init & first commit** — `git init -b main`; local
      `user.email=s@y76.io`; committed as `solomon <s@y76.io>`; added remote
      `git@github.com:sleimanitani/gymbox.git`; `push -u origin main` succeeded.

---

## Session index

Newest first. Transcripts are JSONL at
`~/.claude/projects/-home-engineer-Documents-Kyne-gymbox/<id>.jsonl` — a new
session can `Read` a dead session's transcript for full context.

| Session id | Date | Summary | Outcome |
|---|---|---|---|
| `0558415f-c661-422e-816d-4558654b95ae` | 2026-06-09..13 | Crash recovery + WORKLOG system; docs+commit `8b53a10`; **Gate A**, **Gate B** (exact parity), `reinterpret()` (Step 8), **integration round-trip** (Step 9, MVP-α done). | active |
| `dfe32566-721e-421d-95bc-d416644b027f` | 2026-06-09 | Doc reorientation (offline fitter) + first commit. Completed CLAUDE.md edits. | **crashed** 11:40 (stream idle timeout); Plan 2026-06-08-A steps 2–4 left undone |
