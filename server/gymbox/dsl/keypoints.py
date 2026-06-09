"""MediaPipe Pose (33-keypoint) topology registry.

The index -> name mapping is the MediaPipe Pose Landmarker order. The DSL's
`joint_axis` signal references joints by name; this module resolves names to
indices into the PoseFrame.keypoints array.

This MUST stay in lockstep with the Swift side (GymboxSDK Keypoints.swift) and
with the proto PoseFrame ordering.
"""

from __future__ import annotations

# Canonical MediaPipe Pose landmark order (index 0..32).
KEYPOINT_NAMES: tuple[str, ...] = (
    "nose",                 # 0
    "left_eye_inner",       # 1
    "left_eye",             # 2
    "left_eye_outer",       # 3
    "right_eye_inner",      # 4
    "right_eye",            # 5
    "right_eye_outer",      # 6
    "left_ear",             # 7
    "right_ear",            # 8
    "mouth_left",           # 9
    "mouth_right",          # 10
    "left_shoulder",        # 11
    "right_shoulder",       # 12
    "left_elbow",           # 13
    "right_elbow",          # 14
    "left_wrist",           # 15
    "right_wrist",          # 16
    "left_pinky",           # 17
    "right_pinky",          # 18
    "left_index",           # 19
    "right_index",          # 20
    "left_thumb",           # 21
    "right_thumb",          # 22
    "left_hip",             # 23
    "right_hip",            # 24
    "left_knee",            # 25
    "right_knee",           # 26
    "left_ankle",           # 27
    "right_ankle",          # 28
    "left_heel",            # 29
    "right_heel",           # 30
    "left_foot_index",      # 31
    "right_foot_index",     # 32
)

NUM_KEYPOINTS = len(KEYPOINT_NAMES)
assert NUM_KEYPOINTS == 33, "MediaPipe Pose has 33 landmarks"

_NAME_TO_INDEX: dict[str, int] = {name: i for i, name in enumerate(KEYPOINT_NAMES)}


def index_of(name: str) -> int:
    """Resolve a keypoint name to its index. Raises KeyError if unknown."""
    try:
        return _NAME_TO_INDEX[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(
            f"unknown keypoint {name!r}; valid names: {', '.join(KEYPOINT_NAMES)}"
        ) from exc


def name_of(index: int) -> str:
    """Resolve a keypoint index to its name."""
    return KEYPOINT_NAMES[index]
