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

Outputs go under `data/` (gitignored). Detection runs **per movement-side span**
(active wrist), since `db_curl` is single-arm and the videos alternate arms;
results are merged into one timeline.

## Files
- `skeleton.py` — OpenCV drawing (33-kpt MediaPipe connections, phase→colour, HUD,
  timeline). No gymbox import.
- `visualize.py` — CLI: load fixture (+video) → call the library → render.

## Phase colours
CON = green · ECC = blue · ISO_UNLOADED (bottom hold) = amber · RESET = grey.
