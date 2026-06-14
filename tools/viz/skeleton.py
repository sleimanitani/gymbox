"""Skeleton + HUD drawing helpers for the gymbox visualizer (marketing tool).

Pure OpenCV/NumPy rendering. Knows nothing about the DSL — it just draws a
33-keypoint MediaPipe pose, tinted by a phase colour, plus simple HUD widgets.
This module does not import gymbox; the library is called by visualize.py.
"""
from __future__ import annotations

import cv2
import numpy as np

# MediaPipe Pose (33 landmarks) bone connections — matches Keypoints order.
POSE_CONNECTIONS: list[tuple[int, int]] = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),          # arms + shoulders
    (11, 23), (12, 24), (23, 24),                              # torso
    (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),          # left leg
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),          # right leg
    (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22),  # hands
    (0, 11), (0, 12),                                          # neck-ish
]
RIGHT_ARM = {(12, 14), (14, 16), (16, 18), (16, 20), (16, 22)}
LEFT_ARM = {(11, 13), (13, 15), (15, 17), (15, 19), (15, 21)}

# Phase → BGR colour (OpenCV is BGR).
PHASE_COLORS: dict[str, tuple[int, int, int]] = {
    "CON": (80, 220, 80),          # green  — concentric (lifting)
    "ECC": (230, 160, 60),         # blue   — eccentric (lowering)
    "ISO_UNLOADED": (60, 200, 240),  # amber — bottom hold
    "ISO_LOADED": (60, 140, 240),  # orange — (unused by db_curl)
    "RESET": (150, 150, 150),      # grey   — rest / pause
}
BONE = (235, 235, 235)
JOINT = (250, 250, 250)


def color_for(phase: str) -> tuple[int, int, int]:
    return PHASE_COLORS.get(phase, BONE)


def draw_skeleton(
    img: np.ndarray,
    keypoints: list,           # 33 × (x, y, vis), normalized [0,1]
    *,
    active_side: str | None,   # "Left" | "Right" | "Both" | None
    phase: str,
    vis_thresh: float = 0.3,
) -> None:
    """Draw the pose on `img` (in place). The active arm is tinted by `phase`."""
    h, w = img.shape[:2]
    pcolor = color_for(phase)

    def px(i: int) -> tuple[int, int]:
        x, y, _ = keypoints[i]
        return int(x * w), int(y * h)

    def vis(i: int) -> float:
        return keypoints[i][2]

    active_edges: set = set()
    if active_side in ("Right", "Both"):
        active_edges |= RIGHT_ARM
    if active_side in ("Left", "Both"):
        active_edges |= LEFT_ARM

    for a, b in POSE_CONNECTIONS:
        if vis(a) < vis_thresh or vis(b) < vis_thresh:
            continue
        edge = (a, b)
        is_active = edge in active_edges or (b, a) in active_edges
        col = pcolor if is_active else BONE
        thick = 6 if is_active else 3
        cv2.line(img, px(a), px(b), col, thick, cv2.LINE_AA)

    for i in range(33):
        if vis(i) >= vis_thresh:
            cv2.circle(img, px(i), 4, JOINT, -1, cv2.LINE_AA)


def draw_skeleton_dual(
    img: np.ndarray,
    keypoints: list,
    *,
    left_phase: str,
    right_phase: str,
    vis_thresh: float = 0.3,
) -> None:
    """Draw the pose with EACH arm tinted by its own phase (both arms tracked)."""
    h, w = img.shape[:2]

    def px(i):
        x, y, _ = keypoints[i]
        return int(x * w), int(y * h)

    def vis(i):
        return keypoints[i][2]

    lcol, rcol = color_for(left_phase), color_for(right_phase)
    for a, b in POSE_CONNECTIONS:
        if vis(a) < vis_thresh or vis(b) < vis_thresh:
            continue
        edge = (a, b)
        if edge in RIGHT_ARM or (b, a) in RIGHT_ARM:
            col, thick = rcol, 6
        elif edge in LEFT_ARM or (b, a) in LEFT_ARM:
            col, thick = lcol, 6
        else:
            col, thick = BONE, 3
        cv2.line(img, px(a), px(b), col, thick, cv2.LINE_AA)
    for i in range(33):
        if vis(i) >= vis_thresh:
            cv2.circle(img, px(i), 4, JOINT, -1, cv2.LINE_AA)


def _text(img, s, org, scale=0.8, color=(255, 255, 255), thick=2):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw_hud(
    img: np.ndarray,
    *,
    exercise: str,
    rep_num: int,
    rep_total: int,
    phase: str,
    tut_s: float,
    side: str | None,
) -> None:
    """Top-left HUD: exercise, rep counter, current phase chip, running TUT."""
    _text(img, exercise, (24, 44), 0.95)
    _text(img, f"REP {rep_num}/{rep_total}", (24, 86), 0.85)
    # phase chip
    col = color_for(phase)
    cv2.rectangle(img, (24, 104), (44, 124), col, -1)
    _text(img, phase, (52, 122), 0.7, col)
    _text(img, f"TUT {tut_s:4.1f}s", (24, 158), 0.7)
    if side:
        _text(img, side.upper(), (img.shape[1] - 150, 44), 0.7, (200, 200, 255))


def draw_hud_dual(
    img: np.ndarray,
    *,
    exercise: str,
    left: tuple[int, str, float],    # (reps, phase, tut_s)
    right: tuple[int, str, float],
) -> None:
    """HUD showing BOTH arms: per-arm rep counter, phase chip, running TUT."""
    _text(img, exercise, (24, 44), 0.9)
    for label, (reps, phase, tut), y in (("L", left, 86), ("R", right, 136)):
        col = color_for(phase)
        _text(img, f"{label}  REP {reps}", (24, y), 0.8)
        cv2.rectangle(img, (24, y + 10), (42, y + 28), col, -1)
        _text(img, f"{phase}  {tut:4.1f}s", (50, y + 27), 0.62, col)


def draw_timeline_dual(
    img: np.ndarray,
    *,
    left_phases: list[str],
    right_phases: list[str],
    left_reps: list[tuple[int, int]],
    right_reps: list[tuple[int, int]],
    cur_frame: int,
) -> None:
    """Two stacked phase strips (L over R) with per-arm rep ticks + shared playhead."""
    h, w = img.shape[:2]
    n = max(len(left_phases), len(right_phases))
    if n == 0:
        return
    for strip, (phases, reps) in enumerate(((left_phases, left_reps), (right_phases, right_reps))):
        y0 = h - 46 + strip * 22
        y1 = y0 + 18
        for i, ph in enumerate(phases):
            cv2.rectangle(img, (int(i / n * w), y0), (int((i + 1) / n * w), y1), color_for(ph), -1)
        for s, e in reps:
            for f in (s, e):
                x = int(f / n * w)
                cv2.line(img, (x, y0), (x, y1), (255, 255, 255), 1, cv2.LINE_AA)
    xh = int(cur_frame / n * w)
    cv2.line(img, (xh, h - 48), (xh, h - 4), (40, 40, 240), 2, cv2.LINE_AA)


def draw_timeline(
    img: np.ndarray,
    *,
    frame_phases: list[str],
    rep_bounds: list[tuple[int, int]],   # (start_frame, end_frame)
    cur_frame: int,
) -> None:
    """Bottom strip: phase segments coloured, rep boundary ticks, playhead."""
    h, w = img.shape[:2]
    n = len(frame_phases)
    if n == 0:
        return
    y0, y1 = h - 40, h - 16
    for i, ph in enumerate(frame_phases):
        x0 = int(i / n * w)
        x1 = int((i + 1) / n * w)
        cv2.rectangle(img, (x0, y0), (x1, y1), color_for(ph), -1)
    for s, e in rep_bounds:
        for f in (s, e):
            x = int(f / n * w)
            cv2.line(img, (x, y0 - 6), (x, y1 + 6), (255, 255, 255), 1, cv2.LINE_AA)
    xh = int(cur_frame / n * w)
    cv2.line(img, (xh, y0 - 10), (xh, y1 + 10), (40, 40, 240), 2, cv2.LINE_AA)
