"""Camera-angle classification (architecture.md §9, product.md).

ROADMAP: later step. Classifies the viewing angle (front | three_quarter |
side | back) from skeleton geometry; emits the `camera_angle` annotation layer.
Reference + batch-replay role.
"""

from __future__ import annotations

from .types import SkeletonStream


def classify_camera_angle(stream: SkeletonStream) -> str:
    """Return one of: front | three_quarter | side | back."""
    raise NotImplementedError(
        "pipeline.camera_angle.classify_camera_angle — implement after Gate A "
        "(ROADMAP). Emits the camera_angle layer."
    )
