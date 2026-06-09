"""The gymbox Backend (architecture.md §5).

The integrator's backend imports `Backend`, constructs it with a `Config`, and
mounts its FastAPI router under any prefix. The Backend owns the DB engine,
loads exercise specs on start, and runs the background materializer.

Usage:

    from gymbox import Backend, Config

    backend = Backend(Config(
        db_url="postgresql+asyncpg://...",
        auth_validator=my_app.auth.validate_token,
        exercises_dir="./exercises",
    ))
    await backend.start()
    app.include_router(backend.router, prefix="/ml")
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from .config import Config
from .persistence import Database

logger = logging.getLogger("gymbox")


class Backend:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.db = Database(config.db_url, echo=config.db_echo)
        self._materializer_task: asyncio.Task | None = None
        # Built lazily so the router can close over `self`.
        self._router: APIRouter | None = None

    @property
    def router(self) -> APIRouter:
        """The FastAPI router to mount into the host app. The only API surface
        in MVP-α (architecture.md §8)."""
        if self._router is None:
            # Imported here to avoid a circular import at module load.
            from .api.http import build_router

            self._router = build_router(self)
        return self._router

    async def start(self) -> None:
        """Load exercise specs into the DB and start the materializer.

        Assumes migrations have already been applied (`alembic upgrade head`).
        For the reference box / tests, call `self.db.create_all()` first.
        """
        await self._load_exercises()
        self._materializer_task = asyncio.create_task(self._run_materializer())
        logger.info("gymbox backend started")

    async def stop(self) -> None:
        if self._materializer_task is not None:
            self._materializer_task.cancel()
            try:
                await self._materializer_task
            except asyncio.CancelledError:
                pass
        await self.db.dispose()
        logger.info("gymbox backend stopped")

    # -- internals ----------------------------------------------------------

    async def _load_exercises(self) -> None:
        """Load + validate every spec in exercises_dir and upsert into the DB.

        Validation is via `dsl.load_spec` (the authoring contract). Specs that
        fail validation are logged and skipped — a malformed spec must not take
        the whole backend down.
        """
        from .api.exercises import upsert_exercise_spec
        from .dsl import load_spec

        path = self.config.exercises_path()
        if not path.exists():
            logger.warning("exercises_dir %s does not exist; no specs loaded", path)
            return

        async with self.db.session() as session:
            for spec_file in sorted(path.glob("*.json")):
                try:
                    spec = load_spec(spec_file)
                except Exception as exc:  # noqa: BLE001 - log + skip
                    logger.error("invalid exercise spec %s: %s", spec_file.name, exc)
                    continue
                await upsert_exercise_spec(session, spec)
                logger.info("loaded exercise spec %s", spec.id)
            await session.commit()

    async def _run_materializer(self) -> None:
        """Background loop that denormalizes annotations into sessions/sets/reps.

        Runs every `materializer_interval_s`. Not real-time (architecture.md §5).
        """
        from .materializer import materialize_pending

        interval = self.config.materializer_interval_s
        while True:
            try:
                async with self.db.session() as session:
                    n = await materialize_pending(session)
                    await session.commit()
                    if n:
                        logger.info("materialized %d session(s)", n)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("materializer iteration failed")
            await asyncio.sleep(interval)
