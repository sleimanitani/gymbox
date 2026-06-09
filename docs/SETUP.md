# gymbox — SETUP

How to build, test, and run each piece. Targets: a dev box (Linux/macOS) for the
Python server, a Mac with Xcode for the iOS SDK.

---

## Python server (`server/`)

Requires Python ≥ 3.11.

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # core + pytest + alembic + argon2 + aiosqlite
```

Run the tests:

```bash
python scripts/make_fixture.py     # generates tests/fixtures/bicep_curl_1.json
pytest -q
```

Expected today: most tests pass, the three **Gate A** tests **xfail** (until
`pipeline/rep.py` is implemented), and the **ingest** tests **skip** (until a
Postgres test DB is provided). To run the ingest tests:

```bash
# any reachable async-Postgres URL
export GYMBOX_TEST_DB=postgresql+asyncpg://gymbox:gymbox@localhost/gymbox_test
pytest -q tests/test_ingest.py
```

### Migrations

Production creates tables via Alembic (the reference box uses `create_all` for
convenience):

```bash
export GYMBOX_DB_URL=postgresql+asyncpg://gymbox:gymbox@localhost/gymbox
alembic upgrade head
```

The initial revision creates the `gymbox` schema, all tables (from the ORM
metadata, so no drift), and seeds the 13 annotation layers.

### Embedding in a host backend

```python
from gymbox import Backend, Config

backend = Backend(Config(
    db_url="postgresql+asyncpg://...",
    auth_validator=my_app.auth.validate_token,   # async (token) -> user_id | None
    exercises_dir="./exercises",
    blob_storage_url="local://./data/blobs",      # or s3://… / gcs://…
))
# in your FastAPI/Starlette app:
await backend.start()
app.include_router(backend.router, prefix="/ml")
```

---

## Proto (`gymbox-proto/`)

Generates the upload-envelope bindings. Requires `protoc` (and
`protoc-gen-swift` for Swift).

```bash
cd gymbox-proto
pip install grpcio-tools        # for the Python generator
./scripts/gen_python.sh         # -> python/gymbox_proto/gymbox_pb2.py (gitignored)
./scripts/gen_swift.sh          # -> swift/Sources/GymboxProto/*.pb.swift
```

No gRPC service is defined — message types only.

---

## iOS SDK (`ios/`) — on a Mac with Xcode

```bash
cd ios
swift build          # or open Package.swift in Xcode
swift test           # runs the DSL/signal parity tests; Gate B is pending
```

MediaPipe Pose Lite is **not** a SwiftPM dependency — the host app integrates it
as a binary (`.xcframework`/CocoaPod) and conforms its wrapper to the
`PoseSource` protocol. GymboxSDK depends only on `GymboxProto` and Foundation.

---

## Reference box (`gymbox-box/`)

```bash
cd gymbox-box
GYMBOX_DEMO_TOKEN=demo-token GYMBOX_ADMIN_TOKEN=admin-token \
  docker compose up --build
curl -s localhost:8080/ml/health
```

Demo/eval only — see `gymbox-box/README.md`.

---

## Common URLs / env vars

| Var | Used by | Default |
|---|---|---|
| `GYMBOX_DB_URL` | server, alembic, box | `postgresql+asyncpg://gymbox:gymbox@localhost/gymbox` |
| `GYMBOX_TEST_DB` | ingest tests | unset → tests skip |
| `GYMBOX_EXERCISES_DIR` | server, box | `./exercises` |
| `GYMBOX_BLOB_URL` | server, box | `local://./data/blobs` |
| `GYMBOX_DEMO_TOKEN` / `GYMBOX_ADMIN_TOKEN` | box | unset → box denies all |
