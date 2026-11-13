# Progress log

Newest first. 3–5 lines per session: what was done, what was decided, what's next.

## 2026-11-13: Phase 1, task 9 (design system v1 "Planner"), moved ahead of task 7

- **Done:**
  - committed `docs/DESIGN.md` (direction B) and implemented it:
    - `@theme` tokens, type styles (`type-display` … `type-label`) and the shadcn variable mapping in `index.css`
    - self-hosted Inter and Space Grotesk, so no Google Fonts calls
    - no shadow utilities
  - shared UI restyled:
    - buttons (primary, module, outline, quiet, on-dark), segmented tabs, cards, fields, badges, dialogs
    - new `ModuleBadge`
  - a top navigation replaces the sidebar
  - restyled Today, Modules and module detail. Module detail sets `--module` on its root.
  - Today:
    - the date header, with countdown tiles from real upcoming assessments
    - the day timeline (hour grid + NOW) and the ink next-up card are honest empty states: "Your plan appears here once the planner is built"
  - module colours:
    - 8 swatches; the custom picker refuses colours below 4.5:1 against ink
    - `lib/contrast.ts` + tests (swatches, plus the spec's token ratios)
    - migration 0004 maps existing colours to the nearest swatch by hue
    - the API default is Orange
  - tests: API 231, web 181
- **Decided:**
  - the spec's `muted` token is a text colour; `text-muted-foreground` aliases it, and backgrounds use `surface`
  - colours are matched by hue, not plain Lab distance, which would turn iOS blue into lilac
  - "Reviews due" and the weekly bars wait for real data (Phase 5, session history)
  - only one old preset (#5856D6) actually failed against ink; the others are remapped anyway, as the spec asks
- **Next:** Phase 1 task 7: the session screen, built on the session engine in this design.

## 2026-11-13: Phase 1, task 6 (session engine: timer, offline queue, away detection)

- **Done:**
  - `apps/web/src/session-engine/`:
    - `timer.ts`: pure replay, totals, 50/10 cycles, away detection, stop-the-clock events
    - `outbox.ts`: localStorage queue and flush
    - `heartbeat.ts`, `store.ts` (safe localStorage), `format.ts`
    - `engine.ts`: commands, restore after reload, tick and away prompt, snapshot
  - `fixtures/session-timelines.json`: 25 shared cases run by pytest and vitest. Changing one expected number fails both suites.
  - tests: web 96 in session-engine, covering:
    - pause and resume
    - a reload with an event still queued offline
    - a session started offline
    - laptop sleep, including during a break
    - a closed tab, with keep and end
    - a duplicate retry after a lost reply
    - a rejected batch
    - breaks due but not forced
- **Decided:**
  - totals come only from event times on the client clock
  - the queue is keyed by the start event's id, so a session can start offline
  - 409/422 replies are set aside and not retried
  - an unanswered away prompt survives a reload: the heartbeat isn't refreshed while the prompt is open
  - on a break, "stop the clock" posts `break_end` + `pause` at the last-active time
- **Next:** Phase 1 task 7: the session screen (timer UI, breaks, end, reflection), wiring `tick`, the `online` event and a 30 s flush, plus the real 50-minute clock check.

## 2026-11-13: Phase 1, task 5 (study sessions and session events)

- **Done:**
  - migration 0003: `study_sessions`, `session_events` (append-only, PK `(user_id, id)`), `session_topic_ratings`
  - pure `timeline.replay()` (state + active/break seconds from events), written tests first
  - endpoints: `POST /sessions` (idempotent start), `GET /sessions/active`, `GET|DELETE /sessions/{id}`,
    `POST /sessions/{id}/events` (batch), `PUT /sessions/{id}/reflection`, `GET /modules/{id}/sessions`
  - tests: API 188 (timeline 24, service 25, endpoints 11, plus new cross-user cases), web 61
- **Decided (ADR 0003):**
  - events are the source of truth, and the client never sends durations
  - totals run to the last event, so the server and client clocks never mix
  - resent events are no-ops, and late offline batches are merged in time order and re-validated
  - one open session per user via a partial unique index
- **Next:** Phase 1 task 6: `session-engine/timer.ts` on top of these events (tests first).

## 2026-11-13: Phase 1, task 4 (Today page) + dev port check

- **Done:**
  - Today: upcoming assessments and open tasks across modules, grouped Overdue / Today / Next 7 days / Later; overdue flagged; tick tasks done, mark overdue assessments completed
  - empty states for no modules and for nothing dated
  - API: `GET /modules/{id}/assessments|tasks` (404 if not yours); `/assessments` and `/tasks` are cross-module with `?status=`
  - (PR #5) `npm run dev` refuses to start if :8000 or :5173 already answers, naming the holder
  - tests: API 118, web 61
- **Decided:**
  - undated items aren't deadlines; Today counts undated open tasks instead
  - the old `module_id` / `assessment_id` query filters are removed (one way to list a module's rows)
  - list mutations invalidate the whole `assessments` / `tasks` query prefix, so Today and module tabs stay in sync
- **Next:** Phase 1 task 5: `study_sessions` + `session_events` models and endpoints.

## 2026-11-12: Phase 1, task 3 (dev proxy, assessments and tasks)

- **Done:**
  - same-origin `/api` dev proxy; the health card now treats the proxy's 502 as "API down"
  - assessments and tasks endpoints; topic scope is set atomically with create and update
  - module page tabs: Assessments (dates, weights + total, topic checklist), Tasks (done checkbox, status, overdue), Topics
  - tests: API 113 (21 cross-user requests + 3 list filters); web 49
- **Decided:**
  - due dates must carry a timezone, and the UI sends local date + time as ISO
  - default times: 09:00 for sit-down assessments, 23:59 for hand-ins
  - weights aren't forced to total 100; the UI shows the total
  - ESLint blocks the shadcn CLI's stray `cn` import
- **Next:** Phase 1 task 4: the Today page with upcoming deadlines and empty states.

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
