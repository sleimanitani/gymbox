"""FastAPI router (architecture.md §8). The only API surface in MVP-α.

Endpoints:
    POST   /sessions                     upload a completed session
    GET    /sessions/{id}                session metadata + materialized sets/reps
    GET    /users/me/sessions            list caller's sessions (paginated)
    GET    /sessions/{id}/annotations    full annotation list
    GET    /exercises                    list specs with ETags
    GET    /exercises/{id}               one ExerciseSpec (+ optional model_url)
    GET    /health                       liveness
    POST   /admin/exercises              create/update spec (admin)
    POST   /admin/exercises/{id}/model   upload a model file (admin)

WebSocket /ws/sessions/{id} is deferred (architecture.md §8): the app gets
real-time events from the SDK on the phone, not from the server.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)

from ..dsl import load_spec_dict
from . import exercises as ex
from .schemas import (
    ExerciseListItem,
    SessionUploadIn,
    UploadResult,
)

if TYPE_CHECKING:
    from ..backend import Backend


def build_router(backend: "Backend") -> APIRouter:
    router = APIRouter(tags=["gymbox"])
    config = backend.config

    # -- auth dependency ----------------------------------------------------

    async def require_user(
        authorization: Annotated[str | None, Header()] = None,
    ) -> str:
        """Validate the bearer token via the integrator's auth_validator.
        Returns the user id (architecture.md §12)."""
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        user_id = await config.auth_validator(token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="invalid token")
        return user_id

    async def require_admin(
        user_id: Annotated[str, Depends(require_user)],
    ) -> str:
        if not await config.admin_check(user_id):
            raise HTTPException(status_code=403, detail="admin role required")
        return user_id

    UserDep = Annotated[str, Depends(require_user)]
    AdminDep = Annotated[str, Depends(require_admin)]

    # -- liveness -----------------------------------------------------------

    @router.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "gymbox", "version": _version()}

    # -- OTA exercise spec channel (concrete; locked schema) ----------------

    @router.get("/exercises", response_model=list[ExerciseListItem])
    async def list_exercises(_user: UserDep) -> list[ExerciseListItem]:
        async with backend.db.session() as session:
            rows = await ex.list_exercises(session)
            return [
                ExerciseListItem(
                    id=r.id,
                    display_name=r.display_name,
                    schema_version=r.schema_version,
                    etag=r.etag,
                )
                for r in rows
            ]

    @router.get("/exercises/{exercise_id}")
    async def get_exercise(
        exercise_id: str,
        response: Response,
        _user: UserDep,
        if_none_match: Annotated[str | None, Header()] = None,
    ) -> Response:
        async with backend.db.session() as session:
            row = await ex.get_exercise(session, exercise_id)
            if row is None:
                raise HTTPException(status_code=404, detail="exercise not found")
            # ETag-driven cache validation (architecture.md §10).
            if if_none_match is not None and if_none_match == row.etag:
                return Response(status_code=304, headers={"ETag": row.etag})
            spec_dict = ex.columns_to_spec_dict(row)
            # Attach optional model_url if a model file exists.
            if row.model_spec:
                spec_dict["model_url"] = f"/exercises/{exercise_id}/model"
            body = json.dumps(spec_dict)
            return Response(
                content=body,
                media_type="application/json",
                headers={"ETag": row.etag},
            )

    # -- session upload -----------------------------------------------------

    @router.post("/sessions", response_model=UploadResult)
    async def upload_session(
        request: Request,
        user_id: UserDep,
        envelope: Annotated[str, Form()],
        skeleton_blob: UploadFile | None = None,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> UploadResult:
        """Upload a completed session.

        Multipart form: `envelope` is the JSON SessionUploadIn; `skeleton_blob`
        is the compressed pose stream part. Two dedupe layers (architecture.md §8):
          - Idempotency-Key header  -> transport-retry dedupe
          - envelope.client_session_id -> durable session identity (update on re-upload)
        """
        from .sessions import ingest_session

        try:
            upload = SessionUploadIn.model_validate_json(envelope)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"invalid envelope: {exc}") from exc

        # The token's user must match the envelope's user_id.
        if upload.session.user_id != user_id:
            raise HTTPException(status_code=403, detail="user_id mismatch with token")

        blob_bytes = await skeleton_blob.read() if skeleton_blob is not None else None

        async with backend.db.session() as session:
            result = await ingest_session(
                session,
                config=config,
                upload=upload,
                skeleton_bytes=blob_bytes,
                idempotency_key=idempotency_key,
            )
            await session.commit()
        return result

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str, user_id: UserDep) -> dict:
        from .sessions import read_session

        async with backend.db.session() as session:
            out = await read_session(session, session_id=session_id, user_id=user_id)
            if out is None:
                raise HTTPException(status_code=404, detail="session not found")
            return out.model_dump(mode="json")

    @router.get("/users/me/sessions")
    async def list_my_sessions(
        user_id: UserDep,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        from .sessions import list_user_sessions

        async with backend.db.session() as session:
            items = await list_user_sessions(
                session, user_id=user_id, limit=limit, offset=offset
            )
            return {"items": [i.model_dump(mode="json") for i in items], "offset": offset}

    @router.get("/sessions/{session_id}/annotations")
    async def get_session_annotations(session_id: str, user_id: UserDep) -> dict:
        from .sessions import read_annotations

        async with backend.db.session() as session:
            anns = await read_annotations(session, session_id=session_id, user_id=user_id)
            if anns is None:
                raise HTTPException(status_code=404, detail="session not found")
            return {"annotations": anns}

    # -- admin --------------------------------------------------------------

    @router.post("/admin/exercises")
    async def admin_upsert_exercise(payload: dict, _admin: AdminDep) -> dict:
        try:
            spec = load_spec_dict(payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"invalid spec: {exc}") from exc
        async with backend.db.session() as session:
            row = await ex.upsert_exercise_spec(session, spec)
            await session.commit()
            return {"id": row.id, "etag": row.etag}

    @router.post("/admin/exercises/{exercise_id}/model")
    async def admin_upload_model(
        exercise_id: str,
        _admin: AdminDep,
        model_file: UploadFile,
    ) -> dict:
        # ROADMAP: store the model file in blob storage, insert an exercise_models
        # row, and populate the exercise's model_spec. Empty in MVP-α (§9, §11.2).
        raise HTTPException(
            status_code=501,
            detail="model upload not implemented in MVP-α (exercise_models is schema-only)",
        )

    return router


def _version() -> str:
    from .. import __version__

    return __version__
