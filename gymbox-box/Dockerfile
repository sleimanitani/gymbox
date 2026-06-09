# gymbox reference box — demo/eval/integration-test image. NOT production.
# Production deployments embed the `gymbox` package in the integrator's own
# backend (architecture.md §13).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the gymbox package with the reference-box extras (argon2, uvicorn,
# aiosqlite). The build context root is the repo root so we can copy ../server.
COPY server /src/server
RUN pip install "/src/server[refbox]"

# The reference app entrypoint and the bundled exercise specs.
COPY gymbox-box/app.py /app/app.py
COPY server/exercises /app/exercises

# Blob storage and SQLite (if used) live here; mounted as a volume in compose.
RUN mkdir -p /app/data/blobs

ENV GYMBOX_EXERCISES_DIR=/app/exercises \
    GYMBOX_BLOB_URL=local:///app/data/blobs

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
