"""Optional per-exercise classifier head runner (architecture.md §11.2).

RESERVED — null in MVP-α. When an ExerciseSpec carries a `model_spec`, this
module loads the ONNX head and produces an auxiliary signal the interpreter can
fuse. The MVP-α code path never reaches here (model_spec is None).

DO NOT implement for MVP-α. This exists so the import surface and the
`if model_spec is not None` branch have a home.
"""

from __future__ import annotations

from ..dsl.models import ModelSpec
from .types import SkeletonStream


class ClassifierHead:
    """Wraps a per-exercise ONNX classifier head. Reserved (MVP-β+)."""

    def __init__(self, model_spec: ModelSpec) -> None:
        self.model_spec = model_spec

    def run(self, stream: SkeletonStream):
        raise NotImplementedError(
            "pipeline.classifier.ClassifierHead.run — reserved for MVP-β+. "
            "model_spec is null in MVP-α; this path is never taken."
        )
