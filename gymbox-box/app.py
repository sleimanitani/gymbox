"""ASGI entrypoint for the gymbox reference box.

    uvicorn app:app --host 0.0.0.0 --port 8000

The reference box is for local development, integration testing, and demos —
NOT production. It ships an Argon2id token validator seeded from environment
variables and creates its tables on startup (production uses Alembic). See
architecture.md §13.
"""
from gymbox.refdeploy import make_reference_app

app = make_reference_app()
