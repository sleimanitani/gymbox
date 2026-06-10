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

_None. Next up: ROADMAP Step 7 — port `ios/.../DSLInterpreter.swift` to match
`rep.py` for Gate B (>=98% frame-phase identity, identical rep count, +/-2-frame
boundaries). Gate A is now done, so Gate B is unblocked. Open a plan here before
starting._

---

## Completed plans

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
| `0558415f-c661-422e-816d-4558654b95ae` | 2026-06-09/10 | Recovered from crash; established WORKLOG system; finished Plan 2026-06-08-A (docs + first commit/push `8b53a10`); implemented `rep.interpret` → **Gate A PASS** (Plan 2026-06-10-A). | active |
| `dfe32566-721e-421d-95bc-d416644b027f` | 2026-06-09 | Doc reorientation (offline fitter) + first commit. Completed CLAUDE.md edits. | **crashed** 11:40 (stream idle timeout); Plan 2026-06-08-A steps 2–4 left undone |
