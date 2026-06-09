"""Reference deployment helpers (architecture.md §12, §13).

For `gymbox-box` and demos ONLY — not production. Ships a DefaultTokenValidator
(Argon2id-hashed tokens) and a FastAPI app factory that wires a Backend with
sensible reference defaults.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from .backend import Backend
from .config import Config

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    _ph = PasswordHasher()
    _HAS_ARGON2 = True
except ImportError:  # argon2-cffi not installed
    _ph = None
    _HAS_ARGON2 = False
    VerifyMismatchError = Exception  # type: ignore


class DefaultTokenValidator:
    """Maps opaque bearer tokens to user ids via Argon2id hash comparison.

    Reference-only. The token->user_id mapping is provided at construction
    (e.g. seeded from env or a demo fixture). Production integrators pass their
    own `auth_validator` instead (architecture.md §12).
    """

    def __init__(self, token_hashes: dict[str, str]) -> None:
        # token_hashes: user_id -> argon2id hash of that user's token.
        if not _HAS_ARGON2:
            raise RuntimeError(
                "DefaultTokenValidator requires argon2-cffi "
                "(pip install 'gymbox[refbox]')"
            )
        self._hashes = token_hashes

    @staticmethod
    def hash_token(token: str) -> str:
        if not _HAS_ARGON2:
            raise RuntimeError("argon2-cffi not installed")
        return _ph.hash(token)

    async def __call__(self, token: str) -> str | None:
        for user_id, h in self._hashes.items():
            try:
                _ph.verify(h, token)
                return user_id
            except VerifyMismatchError:
                continue
            except Exception:  # noqa: BLE001 - malformed hash, skip
                continue
        return None


async def _demo_admin_check(user_id: str) -> bool:
    # In the reference box, the user id "admin" (or env override) is admin.
    return user_id == os.environ.get("GYMBOX_ADMIN_USER", "admin")


def make_reference_app() -> FastAPI:
    """Build a FastAPI app wrapping a Backend with reference defaults.

    Env:
      GYMBOX_DB_URL          async SQLAlchemy URL (default: local sqlite+aiosqlite)
      GYMBOX_EXERCISES_DIR   path to specs (default: ./exercises)
      GYMBOX_BLOB_URL        blob storage url (default: local://./data/blobs)
      GYMBOX_DEMO_TOKEN      a demo bearer token mapped to user "demo"
      GYMBOX_ADMIN_TOKEN     a demo admin token mapped to user "admin"
    """
    db_url = os.environ.get(
        "GYMBOX_DB_URL", "postgresql+asyncpg://gymbox:gymbox@localhost/gymbox"
    )
    exercises_dir = os.environ.get("GYMBOX_EXERCISES_DIR", "./exercises")
    blob_url = os.environ.get("GYMBOX_BLOB_URL", "local://./data/blobs")

    # Seed demo tokens if provided.
    token_hashes: dict[str, str] = {}
    demo = os.environ.get("GYMBOX_DEMO_TOKEN")
    admin = os.environ.get("GYMBOX_ADMIN_TOKEN")
    if _HAS_ARGON2:
        if demo:
            token_hashes["demo"] = DefaultTokenValidator.hash_token(demo)
        if admin:
            token_hashes["admin"] = DefaultTokenValidator.hash_token(admin)

    validator = (
        DefaultTokenValidator(token_hashes) if (_HAS_ARGON2 and token_hashes) else None
    )

    config = Config(
        db_url=db_url,
        auth_validator=validator if validator else Config.__dataclass_fields__["auth_validator"].default,
        exercises_dir=exercises_dir,
        blob_storage_url=blob_url,
        admin_check=_demo_admin_check,
    )
    backend = Backend(config)

    app = FastAPI(title="gymbox reference box")

    @app.on_event("startup")
    async def _startup() -> None:
        # Reference box creates tables directly; production uses Alembic.
        await backend.db.create_all()
        await backend.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await backend.stop()

    app.include_router(backend.router, prefix="/ml")
    return app
