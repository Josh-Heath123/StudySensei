# StudySensei

A study planner and tutor: modules → materials → topic map → past papers → plan → sessions → practice → mastery.
Web rebuild of a retired PyQt prototype (tag `v0-pyqt-prototype`). Product: `docs/PRODUCT.md`. Architecture: `docs/ARCHITECTURE.md`. Visual design: `docs/DESIGN.md`.

## Start every task here

1. Read `docs/ROADMAP.md` and pick the next unchecked task in the current phase (one task = one session = one PR).
2. Skim the latest entries in `docs/PROGRESS.md`.
3. Use plan mode for anything touching more than a couple of files, unless the task prompt is fully specified and says "skip plan mode".
4. Work on a branch named `phase-N/<task>`.

## Rules (non-negotiable)

- Camera frames and audio never leave the browser and are never stored.
- AI output is saved only after passing a Pydantic schema. AI never changes the plan, timers or progress directly.
- Every database query is scoped by `user_id`.
- Timer, planner, mastery, metric and signal code is merged only with unit tests.
- Every number shown to the student is labelled measured or estimated, with its sample size.
- No secrets in git: use `.env` and keep `.env.example` current.
- Finish every task by running `npm run check`, ticking `ROADMAP.md` and adding a `PROGRESS.md` entry.
- AI providers are free tiers (decision 0002): never put personal data in prompts (names, student numbers, emails, reflections).
- Course material (e.g. COS330 under `C:\Users\flosh\OneDrive\...\COS330`) is read-only. Never copy it into the repo or commit it.
  Exclude the student's own `u23541475_*` submissions from AI processing.

## Commands (run from the repo root)

| Command | What it does |
| --- | --- |
| `npm install` | Install web and root JS deps (first time) |
| `npm run dev` | Postgres (docker) → migrate → seed → API on :8000 + job worker + web on :5173 |
| `npm run check` | Everything CI runs: ruff, ruff format, prettier, eslint, mypy, tsc, pytest, vitest (not e2e) |
| `npm run e2e` | Playwright against the real stack on its own ports (API :8001, web :5174, db `studysensei_e2e`, rebuilt each run). First time: `npx playwright install chromium` |
| `npm run format` | Auto-fix formatting (ruff + prettier) |
| `npm run gen:api` | Re-export OpenAPI and regenerate the TS client types. Run after any API schema change |
| `npm run db:up` / `db:down` | Start or stop Postgres only |
| `npm run db:migrate` / `db:seed` | Alembic upgrade head / create the local user |

API only (`cd apps/api`):
- `uv run pytest -k health` to run some tests
- `uv run alembic revision --autogenerate -m "add modules"` for a new migration (check the file it writes)
- `uv run uvicorn app.main:app --reload`
- `uv run python -m app.jobs.worker` runs the job worker alone (uploads stay "Waiting to be processed" without it)
- `uv run python -m tests.fixtures.make_fixtures` regenerates the small synthetic PDF/PPTX/DOCX test files (never use course material as fixtures)

Web only: `npm run test:watch -w apps/web`, `npm run build -w apps/web`.

Postgres runs on **localhost:5433** (user, password and db are all `studysensei`). pytest uses the `studysensei_test` database; `npm run e2e` uses `studysensei_e2e` (created on first run).

## Layout

```
apps/api/app/   api/ (routers) · core/ (config, db) · models/ · schemas/ · services/ · ai/ · jobs/
apps/api/       alembic/ · tests/ · evals/ · scripts/export_openapi.py
apps/web/e2e/   Playwright specs (`npm run e2e`)
apps/web/src/   app/ (routes, layout, top nav) · features/<area>/ · lib/api/ (generated client) · ui/ (shadcn)
docs/           PRODUCT · ARCHITECTURE · DESIGN · ROADMAP · PROGRESS · decisions/ · legacy-notes · PLAN (frozen original)
```

## Conventions

### Python (apps/api)
- Python 3.12, fully typed; `mypy --strict` must pass. Use ruff for lint and format (line length 100).
- Async SQLAlchemy 2 with `Mapped[...]` models. New models inherit `TimestampedBase` (UUID id, created_at, updated_at)
  and are imported in `app/models/__init__.py` so Alembic sees them.
- User-owned tables follow the isolation pattern in `app/models/academics.py`: a `UNIQUE (id, user_id)`, and composite
  FKs to parents that include `user_id` or `module_id` (see ARCHITECTURE "User isolation").
- Service functions take `session`, then a keyword-only `user_id`, and filter on it. Another user's ID → `NotFound`.
  Errors live in `app/services/errors.py`. Endpoints get the user from `CurrentUser` (`app/api/deps.py`).
- Every schema change needs an Alembic migration. Never edit a migration that's already merged.
- Routers stay thin: validate with Pydantic, call a service, return a schema. Business logic lives in `app/services/`.
- Settings come from `app/core/config.py` (`get_settings()`), never `os.environ` directly.
- Tests hit real Postgres (no DB mocks). Endpoint tests use the `client_as(user)` / `alice_api` / `bob_api` fixtures
  in `tests/api/conftest.py`; every new endpoint gets a cross-user case in `tests/api/test_cross_user_api.py`.
- PATCH schemas extend `_Update` and list clearable fields in `nullable`; explicit null elsewhere is a 422.
- Raise `NotFound` / `Conflict` / `Invalid` from services; `app/api/errors.py` maps them to 404 / 409 / 422.
  Let unique constraints decide conflicts (catch `IntegrityError` in a `begin_nested()` savepoint), not "exists?" queries.
- Use `logging`, never `print` (except in CLI scripts like `seed.py`).

### TypeScript (apps/web)
- Strict TS with `noUncheckedIndexedAccess`. Use the `@/` alias for `src/`.
- Call the server only through `api` in `src/lib/api/client.ts` (typed from OpenAPI). Never hand-write response types.
  Its base URL is `/api` on the page's origin; in dev, Vite proxies `/api` to :8000 (`API_PROXY_TARGET` overrides).
  Query and mutation hooks live in `features/<area>/api.ts` and wrap calls in `unwrap()` (`lib/api/errors.ts`),
  which throws `ApiError` with a readable message.
- Server state goes in TanStack Query. Zustand is only for client-only state that must outlive a component.
- Feature code lives in `src/features/<area>/`. Shared primitives go in `src/ui/` (shadcn style, `cn()` for classes).
- Tests sit next to the code (`*.test.tsx`), using Testing Library queries by role or label. Stub the API with
  `mockApi({"GET /modules/:id": ...})` from `src/test/mockApi.ts`; it records `calls` and fails on unknown routes.
- Only components are exported from `.tsx` files (fast refresh); shared constants and helpers go in `.ts` files.
- Deterministic logic (`session-engine/`, `vision/signals.ts`) is written as pure functions, tests first.

### Git
- Make small logical commits with messages like `feat(api): …`, `fix(web): …`, `chore: …`, `docs: …`, `ci: …`.
- Never commit `.env`, uploads, course material or anything under `data/`.
- Decisions go in `docs/decisions/NNNN-title.md` (context, decision, alternatives, consequences). They're never edited afterwards; supersede them with a new one.
- Update `PRODUCT.md` / `ARCHITECTURE.md` in the same PR as a change that alters them.

## Pull requests (do this without asking)
- When a task's work is committed on its `phase-N/<task>` branch: push it (`git push -u origin <branch>`), open the PR with `gh pr create` (or update the existing one), then watch CI with `gh pr checks --watch`.
- If CI fails, fix it, commit, push and watch again until it's green. Finish by reporting the PR link and the CI result.
- Never push to main, never force-push, never merge a PR. Malcolm merges after review.

## Dev servers
- Don't start `npm run dev` yourself. Malcolm runs it in his own terminal. If you need the running app and nothing answers on :5173, say so instead of starting it.

## Hooks and permissions (`.claude/settings.json`)

- **Stop hook:** when `git status --porcelain` shows changes, `scripts/stop-check.mjs` runs `npm run check`. A failure
  blocks the session from finishing once; if it still fails after that retry, the session stops with a warning.
- **Check lock:** `npm run check` runs through `scripts/with-lock.mjs`, which holds `.locks/check.lock` (gitignored, the PID).
  A second check waits for the first (up to 10 minutes; the hook's timeout is 1500 s to allow for that), because two
  runs at once would both rebuild `studysensei_test`. A lock whose PID is gone is removed. Run the steps without the lock
  with `npm run check:steps`.
- **Allowlisted without prompts:** `uv run`, `npm run`, `git status/diff/log/add/commit`. Everything else (push, tag,
  reset, checkout…) still asks.

## Gotchas

- pytest treats module-level functions named `setup_module` / `teardown_module` as hooks. Don't use those names for helpers.
- On Windows, stopping a background `npm run dev`/`vite`/`uvicorn` task can leave its child process holding the port.
  This sandbox's `netstat -ano` shows listening sockets as `CLOSED` with their PID.
  uvicorn's `SO_REUSEADDR` lets a second server bind a busy port on Windows while the old one keeps answering,
  so `npm run dev` connects to :8000 and :5173 first and refuses to start, naming the holder (`scripts/ports.mjs`).
- The shadcn CLI (every time so far) imports `cn` from an npm package called `cn`; ESLint now rejects that import.
  After `shadcn add`: `npm uninstall -w apps/web cn`, and import `cn` from `@/lib/utils` in the new component.

- Windows: use the asyncpg driver (`postgresql+asyncpg://`). psycopg's async mode fails on the default Proactor event loop.
- `.gitattributes` forces LF. Don't fight it with editor settings.
- If `npm run dev` fails at "Starting Postgres", Docker Desktop isn't running.
- `openapi.json` and `schema.d.ts` are generated files: run `npm run gen:api`, don't edit them by hand. CI checks they're current.
