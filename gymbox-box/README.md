# gymbox-box — reference deployment

A Docker Compose stack — Postgres + the `gymbox` Python library behind nginx —
for **demos, evaluation, and integration testing**. It is *not* how you run
gymbox in production: there, you embed the `gymbox` package in your own backend,
point it at your own Postgres, and front it with your own auth (see
`../docs/architecture.md` §13).

## Run

```bash
cd gymbox-box
GYMBOX_DEMO_TOKEN=my-demo-token GYMBOX_ADMIN_TOKEN=my-admin-token \
  docker compose up --build
```

Then:

```bash
curl -s localhost:8080/ml/health
curl -s localhost:8080/ml/exercises -H "Authorization: Bearer my-demo-token"
```

The box mounts the router under `/ml` (so endpoints are `/ml/sessions`,
`/ml/exercises`, …) and seeds the bundled `db_curl` spec on startup. Tables are
created automatically on first boot (production uses Alembic migrations from
`../server/migrations`).

## What's inside

| Service | Role |
|---|---|
| `db` | Postgres 16, the gymbox schema. |
| `box` | `uvicorn app:app` — the reference FastAPI app from `gymbox.refdeploy`. |
| `nginx` | Reverse proxy on `:8080`, 64 MB upload limit. |

## Tokens

The reference box ships an Argon2id token validator. `GYMBOX_DEMO_TOKEN` maps to
user `demo`; `GYMBOX_ADMIN_TOKEN` maps to user `admin` (admin endpoints require
the latter). If neither is set, the default validator denies all requests — the
box never runs "open".

## Limits

Demo-grade only. No TLS, no migrations on the hot path, no horizontal scaling,
single nginx worker. Fine for evaluation and small pilots (≤ 50 users); not a
production posture.
