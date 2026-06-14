# gymbox visualizer (marketing / demo tool)

Renders annotated skeleton videos — pose overlay, per-phase colouring, rep &
exercise begin/end markers, a HUD (exercise / rep counter / phase / running TUT),
and a timeline strip.

**This is a consumer of the library, not part of it.** It imports and calls
`gymbox.pipeline.rep.interpret`; it never modifies or reimplements detection. It
lives outside the `gymbox` / `GymboxSDK` packages on purpose (like `scripts/`).

## Setup

Uses the server venv plus OpenCV:

```bash
cd server && uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
uv pip install --python .venv opencv-python-headless
```

Inputs:
- a **fixture** JSON (skeleton stream + per-frame `t_s`) from
  `server/scripts/build_fixtures.py` — already has all 33 keypoints;
- optionally the original **video** as background (else a dark canvas).

## Use

```bash
# annotated mp4 (skeleton on the dimmed source video)
server/.venv/bin/python tools/viz/visualize.py \
  --fixture data/fixtures/Bicep_Curl_5.json \
  --video   "training_data/Biceps_curls/Bicep Curl 5.mp4" \
  --out      data/viz/bicep_curl_5.mp4

# fixture only (no video) — renders on a dark canvas
server/.venv/bin/python tools/viz/visualize.py \
  --fixture data/fixtures/Bicep_Curl_5.json --out data/viz/bicep_curl_5.mp4

# dump a single annotated frame to a PNG (for stills / inspection)
server/.venv/bin/python tools/viz/visualize.py \
  --fixture data/fixtures/Bicep_Curl_5.json \
  --video   "training_data/Biceps_curls/Bicep Curl 5.mp4" \
  --out data/viz/frame.png --png-frame 192
```

Outputs go under `data/` (gitignored).

### Both arms (default) vs single-arm

By default the visualizer tracks **both wrists independently** (label-free): it
runs the interpreter once per wrist over the whole clip, tints each arm by its own
phase, and shows **L / R rep counters** and two timeline strips. This covers
simultaneous, alternating, and single-arm curls and needs no `movement_side`
labels (the phone won't have them).

`--single-arm` uses the older path instead: track only the active wrist per
labelled movement-side span.

### Occluded arm: confidence-adaptive filter (recovery, not dropping)

The fixtures contain **both arms** every frame. When an arm is occluded (side-on
view) MediaPipe emits low-confidence coordinates — but they still *track the
arm's motion*, just noisily. So instead of dropping the arm, the viz **denoises
it with a heavier smoothing window** (confidence-adaptive: median wrist+elbow
visibility < 0.5 → S-G window `OCCLUDED_WINDOW`=15 instead of the spec's 9) and
draws it at a lower threshold, flagged **`(est)`**.

Validated on side-on Bicep Curl 8 (left arm visibility 0.12):
`window 9 → 24 phantom reps` → `window 15 → 13` (the true count). The recovered
arm is rendered and labelled estimated rather than hidden.

> Symmetry could further help, but only for *simultaneous* bilateral curls
> (left↔right corr +0.96 on Bicep Curl 5 vs −0.19 on alternating Bicep Curl 9),
> so it's a conditional prior, not implemented. Beyond visibility, an
> `active`/`inactive` motion gate (which *visible* arm is actually working) is a
> library/MVP-β item — see `docs/NOTES.md`.

## Batch reel

Render every fixture into one normalized, title-carded sizzle reel:

```bash
server/.venv/bin/python tools/viz/batch.py \
  --fixtures data/fixtures \
  --videos   training_data/Biceps_curls \
  --out      data/viz/reel.mp4 \
  --canvas   540x960          # portrait; clips are letterboxed to this
```

Each clip gets a `gymbox` title card (exercise / clip name / rep count) followed
by its annotated frames. Per-clip mp4s are still available via `visualize.py`.

## Files
- `skeleton.py` — OpenCV drawing (33-kpt MediaPipe connections, phase→colour, HUD,
  timeline). No gymbox import.
- `visualize.py` — CLI: load fixture (+video) → call the library → render one mp4
  or a still. Exposes `iter_annotated_frames()` for reuse.
- `batch.py` — concatenates all fixtures into one reel with title cards.

## Phase colours
CON = green · ECC = blue · ISO_UNLOADED (bottom hold) = amber · RESET = grey.
