"""gymbox-proto — Python bindings for the gymbox wire format.

Generated code lives in `gymbox_proto.gymbox_pb2` after running
`scripts/gen_python.sh`. The module re-exports the message classes for
convenience once generated.

NOTE: The generated `gymbox_pb2.py` is NOT checked in. Run codegen first:
    cd gymbox-proto && ./scripts/gen_python.sh
"""

from __future__ import annotations

__version__ = "0.1.0"
__proto_package__ = "gymbox.v1"

try:  # pragma: no cover - import shim, exercised only after codegen
    from .gymbox_pb2 import (  # type: ignore  # noqa: F401
        Annotation,
        AnnotationSource,
        DeviceInfo,
        Keypoint,
        PoseFrame,
        SessionMeta,
        SessionUpload,
        SkeletonBlob,
        SkeletonBlobRef,
        UserCorrection,
    )

    _GENERATED = True
except ImportError:  # codegen not yet run
    _GENERATED = False


def is_generated() -> bool:
    """Return True if the protobuf bindings have been generated."""
    return _GENERATED
