# Progress log

Newest first. 3–5 lines per session: what was done, what was decided, what's next.

## 2026-11-12: Phase 0 wrap-up (tag, checks, hook)

- **Done:**
  - created and pushed `v0-pyqt-prototype` (annotated, on `1d55ce1`) and pushed `rebuild`
  - `npm run check` and `npm run dev` pass on Windows with Docker
  - `/health` returns 503 when Postgres is stopped and recovers when it restarts
  - added the Stop hook and a narrow permission allowlist
- **Decided:**
  - the Stop hook runs only when the tree is dirty
  - the hook blocks once, then lets the session stop with a warning, so a broken environment can't trap a session
- **Next:** CI green on the first PR (rebuild → main), then Phase 1 task 1 (models and migrations).

## 2026-11-12: Phase 0 (reset and foundations)

- **Done:**
  - archived the PyQt prototype under `v0-pyqt-prototype`, branch `rebuild`, untracked `.venv`, LF via `.gitattributes`
  - removed legacy code and wrote `docs/legacy-notes.md`
  - scaffolded `apps/api` (FastAPI, `/health` with DB check, Alembic `users`, seed) and `apps/web` (sidebar shell, status card)
  - added docker-compose, the root `npm run dev` / `check`, CI, and split PLAN.md into the working docs
- **Decided:**
  - Postgres on host port 5433
  - asyncpg driver (Windows event loop)
  - OpenAPI client via `openapi-typescript` + `openapi-fetch`
  - no worker until Phase 2
  - ADR 0002 records the free-tier AI providers
- **Next:** push `rebuild` and open a PR so CI runs; add the Stop hook and permission allowlist; then Phase 1 task 1 (models and migrations).
