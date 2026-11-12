# StudySensei

A study planner and tutor: modules → materials → topic map → past papers → plan → sessions → practice → mastery.
Web rebuild of a retired PyQt prototype (tag `v0-pyqt-prototype`). Product: `docs/PRODUCT.md`. Design: `docs/ARCHITECTURE.md`.

## Start every task here

1. Read `docs/ROADMAP.md` and pick the next unchecked task in the current phase (one task = one session = one PR).
2. Skim the latest entries in `docs/PROGRESS.md`.
3. Use plan mode for anything touching more than a couple of files.
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
| `npm run dev` | Postgres (docker) → migrate → seed → API on :8000 + web on :5173 |
| `npm run check` | Everything CI runs: ruff, ruff format, prettier, eslint, mypy, tsc, pytest, vitest |
| `npm run format` | Auto-fix formatting (ruff + prettier) |
| `npm run gen:api` | Re-export OpenAPI and regenerate the TS client types. Run after any API schema change |
| `npm run db:up` / `db:down` | Start or stop Postgres only |
| `npm run db:migrate` / `db:seed` | Alembic upgrade head / create the local user |

API only (`cd apps/api`):
- `uv run pytest -k health` to run some tests
- `uv run alembic revision --autogenerate -m "add modules"` for a new migration (check the file it writes)
- `uv run uvicorn app.main:app --reload`

Web only: `npm run test:watch -w apps/web`, `npm run build -w apps/web`.

Postgres runs on **localhost:5433** (user, password and db are all `studysensei`). pytest uses the `studysensei_test` database.

## Layout

```
apps/api/app/   api/ (routers) · core/ (config, db) · models/ · schemas/ · services/ · ai/ · jobs/
apps/api/       alembic/ · tests/ · evals/ · scripts/export_openapi.py
apps/web/src/   app/ (routes, layout, sidebar) · features/<area>/ · lib/api/ (generated client) · ui/ (shadcn)
docs/           PRODUCT · ARCHITECTURE · ROADMAP · PROGRESS · decisions/ · legacy-notes · PLAN (frozen original)
```

## Conventions

### Python (apps/api)
- Python 3.12, fully typed; `mypy --strict` must pass. Use ruff for lint and format (line length 100).
- Async SQLAlchemy 2 with `Mapped[...]` models. New models inherit `TimestampedBase` (UUID id, created_at, updated_at)
  and are imported in `app/models/__init__.py` so Alembic sees them.
- Every schema change needs an Alembic migration. Never edit a migration that's already merged.
- Routers stay thin: validate with Pydantic, call a service, return a schema. Business logic lives in `app/services/`.
- Settings come from `app/core/config.py` (`get_settings()`), never `os.environ` directly.
- Tests hit real Postgres (no DB mocks). Use `httpx.AsyncClient` + `ASGITransport` for endpoint tests.
- Use `logging`, never `print` (except in CLI scripts like `seed.py`).

### TypeScript (apps/web)
- Strict TS with `noUncheckedIndexedAccess`. Use the `@/` alias for `src/`.
- Call the server only through `api` in `src/lib/api/client.ts` (typed from OpenAPI). Never hand-write response types.
- Server state goes in TanStack Query. Zustand is only for client-only state that must outlive a component.
- Feature code lives in `src/features/<area>/`. Shared primitives go in `src/ui/` (shadcn style, `cn()` for classes).
- Tests sit next to the code (`*.test.tsx`), using Testing Library queries by role or label and stubbing `fetch` with `vi.stubGlobal`.
- Deterministic logic (`session-engine/`, `vision/signals.ts`) is written as pure functions, tests first.

### Git
- Make small logical commits with messages like `feat(api): …`, `fix(web): …`, `chore: …`, `docs: …`, `ci: …`.
- Never commit `.env`, uploads, course material or anything under `data/`.
- Decisions go in `docs/decisions/NNNN-title.md` (context, decision, alternatives, consequences). They're never edited afterwards; supersede them with a new one.
- Update `PRODUCT.md` / `ARCHITECTURE.md` in the same PR as a change that alters them.

## Gotchas

- Windows: use the asyncpg driver (`postgresql+asyncpg://`). psycopg's async mode fails on the default Proactor event loop.
- `.gitattributes` forces LF. Don't fight it with editor settings.
- If `npm run dev` fails at "Starting Postgres", Docker Desktop isn't running.
- `openapi.json` and `schema.d.ts` are generated files: run `npm run gen:api`, don't edit them by hand. CI checks they're current.
