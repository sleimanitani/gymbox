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

### Plan 2026-06-08-A — Doc reorientation + first commit
**Goal:** make the offline ML fitter first-class in the docs, clarify the
interpreter, then make and push the first git commit.
**Origin session:** `dfe32566-721e-421d-95bc-d416644b027f` (crashed 11:40,
stream idle timeout). **Continued by:** `0558415f-c661-422e-816d-4558654b95ae`.
**Decisions (locked by user):** remote already exists → just push · cleanup =
docs only, no code · author `solomon <s@y76.io>` · default branch `main` ·
remote `git@github.com:sleimanitani/gymbox.git`.

- [x] **CLAUDE.md** — added "what interpreter/spec mean" + "offline spec fitting
      (where ML lives)" sections; recast "no ML" → "no *runtime* ML on
      phone/ingest/oracle; offline fitter is in scope". *(done by dfe32566; both
      edits verified on disk)*
- [x] **architecture.md** — reframe "(future) training" so offline spec fitting
      is MVP-α scope; add a section for the fitter pipeline (labeled videos →
      fit thresholds/bands/smoothing → human audit → OTA); keep the runtime
      `model_spec` classifier head explicitly MVP-β+ so the two don't conflate.
      *(done: §1 goal + non-goal, new §10 "Offline spec fitting" subsection, §14)*
- [x] **README.md** — one line on the offline fitter in the architecture-in-one-
      breath paragraph + gates section, without bloating it. *(done: in-one-breath
      para, gates section, docs table + Claude pointer mention WORKLOG)*
- [~] **git init & first commit** — `git init -b main`; set local
      `user.email=s@y76.io`; stage all non-gitignored; commit as
      `solomon <s@y76.io>`; add remote `git@github.com:sleimanitani/gymbox.git`;
      `push -u origin main`.

---

## Completed plans

_None yet._

---

## Session index

Newest first. Transcripts are JSONL at
`~/.claude/projects/-home-engineer-Documents-Kyne-gymbox/<id>.jsonl` — a new
session can `Read` a dead session's transcript for full context.

| Session id | Date | Summary | Outcome |
|---|---|---|---|
| `0558415f-c661-422e-816d-4558654b95ae` | 2026-06-09 | Recovered from crash: read `dfe32566` transcript, established this WORKLOG system. | active |
| `dfe32566-721e-421d-95bc-d416644b027f` | 2026-06-09 | Doc reorientation (offline fitter) + first commit. Completed CLAUDE.md edits. | **crashed** 11:40 (stream idle timeout); Plan 2026-06-08-A steps 2–4 left undone |
