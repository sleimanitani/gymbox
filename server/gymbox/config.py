"""gymbox configuration (architecture.md §5, §12).

The integrator constructs a `Config` and passes it to `Backend`. The
`auth_validator` callback is the integration seam for auth: the host backend's
auth system is the source of truth; gymbox is opaque to token internals.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

# auth_validator: maps a bearer token -> the integrator's user id, or None if
# the token is invalid. (architecture.md §12)
AuthValidator = Callable[[str], Awaitable[str | None]]


async def _reject_all(_token: str) -> str | None:
    """Default validator: rejects everything. Integrators MUST supply their own
    (or use the reference DefaultTokenValidator from gymbox.refdeploy)."""
    return None


@dataclass(slots=True)
class Config:
    # Async SQLAlchemy URL, e.g. "postgresql+asyncpg://user:pw@host/db".
    db_url: str

    # Maps bearer tokens to user ids. Required in practice; defaults to reject-all.
    auth_validator: AuthValidator = _reject_all

    # Directory of exercise spec JSON files loaded into the DB on start().
    exercises_dir: Path | str = "./exercises"

    # Where skeleton blobs land. "local://./data/blobs" or "s3://bucket/prefix"
    # or "gcs://bucket/prefix". The reference box defaults to local FS.
    blob_storage_url: str = "local://./data/blobs"

    # Materializer cadence (seconds). The denormalizer runs in the background.
    materializer_interval_s: float = 120.0

    # Idempotency-Key cache TTL (seconds) for transport-level dedupe.
    idempotency_ttl_s: float = 600.0

    # SQLAlchemy echo for debugging.
    db_echo: bool = False

    # Role check: given a validated user id + token, is this an admin?
    # Admin endpoints (/admin/exercises*) require this. Defaults to deny.
    admin_check: Callable[[str], Awaitable[bool]] = field(
        default_factory=lambda: _deny_admin
    )

    def exercises_path(self) -> Path:
        return Path(self.exercises_dir)


async def _deny_admin(_user_id: str) -> bool:
    return False
