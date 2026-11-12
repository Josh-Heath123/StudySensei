# Progress log

Newest first. 3–5 lines per session: what was done, what was decided, what's next.

## 2026-11-12: Phase 1, task 2 (modules and topics endpoints + Modules UI)

- **Done:**
  - REST endpoints for modules and topics (a tree, plus a move endpoint)
  - a Modules list and form
  - a module page with a manual topic tree: add, rename, reorder, indent, outdent, delete
  - PR #2 review fixes: an explicit null in a PATCH → 422; a duplicate module code → 409 with a clear message, decided by the unique constraint
  - tests: 81 API tests (9 HTTP cross-user cases that get the same 404 as a missing ID), 23 web tests
- **Decided:**
  - module codes are stored upper-case, so duplicates are case-insensitive
  - topic moves use buttons (drag-and-drop waits for design system v1)
  - positions are renumbered 0..n-1 on every move or delete
- **Next:** Phase 1 task 3: assessments and tasks endpoints and UI.

## 2026-11-12: Phase 1, task 1 (academic models and user scoping)

- **Done:**
  - migration 0002 (modules, topic tree, assessments, assessment_topics, tasks)
  - user-scoped services, Pydantic input schemas and the `CurrentUser` dependency
  - 46 new tests: cross-user read, update, delete and link attempts; DB constraints; tree rules; cascades; schema guards
  - the test DB is rebuilt each run, and every test rolls back
- **Decided:**
  - isolation is enforced in Postgres too, via composite FKs, not just by query filters
  - another user's ID is indistinguishable from a missing one
  - scoping is proved at the data layer now; endpoint tasks add HTTP-level cross-user tests
  - services commit
- **Next:** Phase 1 task 2: modules and topics REST endpoints plus the Modules UI.

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
