"""gymbox — server-side library for gym exercise tracking.

Edge-first architecture: the phone does all real-time inference; this library is
storage + an `/exercises` OTA spec channel + (future) training. There is no
gRPC service and no streaming pipeline in MVP-α (architecture.md §3, §5, §14).

Public surface:

    from gymbox import Backend, Config

See architecture.md and ROADMAP.md for the build plan.
"""

from __future__ import annotations

from .backend import Backend
from .config import Config

__all__ = ["Backend", "Config", "__version__"]

__version__ = "0.1.0"
