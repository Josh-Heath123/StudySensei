# Architecture

The "how". Change it in the same PR as any change that alters it. Source: PLAN.md §3, updated by decision 0002.

## Overview

```
Browser (React PWA)                         Server                              External
├─ UI, TanStack Query  ── REST/SSE ──────►  FastAPI (apps/api)  ───────────►  Gemini API (free tier)
├─ session-engine: timer, interventions     ├─ services: planning, mastery…     Groq (fallback)
├─ vision worker (MediaPipe, on-device)     ├─ ai: LLMClient, retrieval         Ollama (optional, local)
└─ voice: Web Speech API, speechSynthesis   └─ worker (Phase 2): jobs table
                                                      │
                                            Postgres 16 + pgvector (docker-compose)
```

The browser does the real-time work: timers, nudges, camera and voice. The server owns stored data, search, AI calls and
background work. **Camera frames and audio never leave the browser.**

## Key decisions

| Area | Choice | Why |
| --- | --- | --- |
| Platform | Web app (PWA), Chromium first | Easiest to polish; nothing to install; camera runs on-device. Tauri is the fallback if spike S1 fails ([0001](decisions/0001-web-rebuild.md)) |
| Front end | React + TypeScript + Vite, Tailwind v4 + shadcn/ui, React Router, TanStack Query, Zustand | Largest ecosystem; no SSR needed |
| Back end | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg) + Alembic, `uv` | Best document and ML libraries; Pydantic validates AI output |
| Database | Postgres 16 + pgvector + built-in full-text search | One service for relational data, vectors, keywords and jobs |
| Background jobs | Worker polling a `jobs` table with `FOR UPDATE SKIP LOCKED` (Phase 2) | No Redis; jobs survive restarts |
| Embeddings | Local `fastembed`, `BAAI/bge-small-en-v1.5` (384 dims, CPU) | Free, private, fast enough |
| LLM access | Our own `LLMClient` with **one OpenAI-compatible adapter** | ~200 lines we control ([0002](decisions/0002-free-ai-providers.md)) |
| Models | Gemini Flash (tutor, topic maps, scanned pages), Gemini Flash-Lite (bulk classification), Groq fallback | Zero cost |
| PDF / Office | `pypdfium2`, `python-pptx`, `python-docx` | Permissive licences (PyMuPDF is AGPL; Docling pulls in PyTorch) |
| Scanned pages | Detect pages with no text layer; opt-in vision-LLM transcription | Tesseract handles maths and handwriting badly |
| Spaced repetition | FSRS (`py-fsrs` / `ts-fsrs`) | Fewer reviews for the same retention |
| Camera | MediaPipe Tasks Vision (FaceLandmarker + blendshapes, PoseLandmarker lite) in a Web Worker | Free, private, proper blink and head-pose signals |
| Speech | Push-to-talk; Web Speech API for STT, `speechSynthesis` for TTS | Zero cost; upgradeable behind interfaces |
| Auth and hosting | Single local user until Phase 9, then Supabase + one small container | One free tier covers DB, auth and storage |

## Repository layout

```
apps/api/            FastAPI service (+ worker from Phase 2), one Python package `app`
  app/api/           routers (health; later modules, materials, sessions, plan, tutor, practice, profile)
  app/core/          config (pydantic-settings), db (async engine/session)
  app/models/        SQLAlchemy models (TimestampedBase: UUID id, created_at, updated_at)
  app/schemas/       Pydantic request/response + AI output schemas
  app/services/      planning/, mastery/, profile/, ingestion/, pastpapers/
  app/ai/            llm_client.py, adapters/, prompts/, retrieval.py, budget.py
  app/jobs/          worker.py, tasks/
  alembic/           migrations
  tests/             pytest against real Postgres (studysensei_test)
  evals/             fixed AI test sets + results/
  scripts/           export_openapi.py
apps/web/            React app
  src/app/           routes, layout, sidebar, providers
  src/features/      today/, modules/, session/, plan/, practice/, insights/, settings/
  src/vision/        camera.ts, vision.worker.ts, signals.ts, calibration.ts, rollup.ts   (Phase 7)
  src/voice/         stt.ts, tts.ts                                                       (Phase 3)
  src/session-engine/ timer.ts, interventions.ts                                         (Phase 1/7)
  src/lib/api/       openapi.json, generated schema.d.ts, typed client (openapi-fetch)
  src/ui/            design-system components (shadcn/ui)
infra/db/init.sql    creates studysensei_test
docker-compose.yml   Postgres 16 + pgvector on host port 5433
scripts/dev.mjs      `npm run dev`: db → migrate → seed → api + web
```

Folders marked with a phase are created when that phase starts.

## API contract

FastAPI generates OpenAPI. `npm run gen:api` writes `apps/web/src/lib/api/openapi.json` and regenerates `schema.d.ts`, and
the web app calls the API through the typed `openapi-fetch` client. CI fails if the committed schema is stale.

`GET /health` returns `{status, api, database, database_error}`: 200 when Postgres answers `SELECT 1` within 2 s, otherwise 503.

**Endpoints so far:**

| Area | Routes |
| --- | --- |
| Modules | `GET/POST /modules`, `GET/PATCH/DELETE /modules/{id}` |
| Topics | `GET /modules/{id}/topics` (nested tree), `POST /modules/{id}/topics`, `PATCH/DELETE /topics/{id}`, `POST /topics/{id}/move` `{parent_id, position}` |
| Assessments | `GET/POST /modules/{id}/assessments`, `GET /assessments?status=` (all modules), `GET/PATCH/DELETE /assessments/{id}` (responses include `topic_ids`; sending `topic_ids` replaces the whole set) |
| Tasks | `GET/POST /modules/{id}/tasks`, `GET /tasks?status=` (all modules), `GET/PATCH/DELETE /tasks/{id}` (`status: "done"` sets `completed_at`) |

Notes on these endpoints:
- A module's own lists live under `/modules/{id}/…` and return 404 if the module isn't yours. The top-level
  `/assessments` and `/tasks` are cross-module lists (used by Today); repeat `status` to filter, e.g.
  `?status=todo&status=in_progress`.
- Dates (`due_at`) must include a timezone; a bare local time is a 422.
- Lists come soonest first, with undated items last.
- List filters with someone else's ID return `[]`, exactly like a non-existent ID.

Topic `position` is the index among siblings. New topics append, and moves/deletes renumber the siblings to 0..n-1.

**Errors** always use `{"detail": ...}`:

| Status | Meaning | `detail` |
| --- | --- | --- |
| 404 | Not found, **or another user's row** (deliberately indistinguishable) | a string |
| 409 | Uniqueness conflict, e.g. a duplicate module code (case-insensitive) | a string |
| 422 | Invalid input: Pydantic validation, an explicit `null` for a required field, or a disallowed operation (e.g. moving a topic into its own subtree) | a list of issues for validation, a string otherwise |

PATCH bodies only change the fields sent. `null` is accepted only for clearable fields (each `*Update` schema's `nullable` set).

## Data model

Every table has:
- a UUID primary key
- `user_id` (except child tables reached through a parent)
- `created_at` and `updated_at`

Derived tables can always be rebuilt from source tables.

| Area | Tables | Notes |
| --- | --- | --- |
| People and settings | `users`, `ai_credentials`, `consents`, `push_subscriptions` | Keys Fernet-encrypted; consent per feature with timestamps |
| Academic structure | `modules`, `topics` (tree via `parent_id`), `assessments`, `assessment_topics`, `tasks` | `topics.source` is `ai` or `user`; user edits never overwritten |
| Materials | `materials`, `chunks` (text, page range, `embedding vector(384)`, `tsv tsvector`), `chunk_topics` | `materials.kind`: slides, notes, guide, tutorial, past paper, test, assignment, outline; SHA-256 dedupe |
| Past papers | `past_questions`, `past_question_topics` | Profile computed by queries, never stored as AI output |
| Planning | `availability_rules`, `availability_exceptions`, `plan_blocks` | `plan_version` on each block |
| Sessions | `study_sessions`, `session_events`, `session_minutes` | No images or audio, ever |
| Practice | `practice_items`, `reviews` (grade + FSRS state) | |
| Derived | `topic_mastery`, `profile_metrics` (value, sample size, label), `recommendations` | Rebuilt nightly and after each session |
| AI | `conversations`, `messages` (with citations), `ai_usage` | Usage drives budget and rate-limit handling |
| System | `jobs` (kind, payload, status, attempts, run_after, error) | |

**Built so far:**
- `users` + the `vector` extension (migration 0001)
- `modules`, `topics`, `assessments`, `assessment_topics`, `tasks` (0002)
- `study_sessions`, `session_events`, `session_topic_ratings` (0003)

### Session events

Decision 0003. `session_events` is an append-only log and the source of truth. The client never sends durations.

- **Events:** `start`, `pause`, `resume`, `break_start`, `break_end`, `end`. Each has a client UUID and a client-clock
  `occurred_at`.
- **Replay:** `services/sessions/timeline.py` is a pure reducer from events to state (`active`, `paused`, `on_break`,
  `ended`) and to `active_seconds` / `break_seconds`. Those are cached on `study_sessions` and computed up to
  `last_event_at`. The timer adds the live tail on the client clock.
- **Idempotent:** resent events are no-ops, and offline batches are merged in time order and re-validated as a whole.
  Event PK `(user_id, id)`.
- **One open session per user:** a partial unique index. `GET /sessions/active` returns it after a reload.
- **Reflection:** focus 1–5 and what was covered on the session; confidence 1–5 per topic in `session_topic_ratings`.
  It's personal data, so it never goes into prompts.
- `plan_block_id` is nullable until Phase 4 adds `plan_blocks`.

### User isolation

Scoping by `user_id` is enforced twice: by the services and by Postgres.

- **Services:** every function in `app/services/` takes a keyword-only `user_id` and filters every query on it.
  Another user's ID raises `NotFound`, exactly like a missing ID, so IDs can't be probed.
  The API maps `NotFound` / `Conflict` / `Invalid` to 404 / 409 / 422.
- **Postgres:**
  - Every user-owned table has `UNIQUE (id, user_id)`.
  - Children reference parents through **composite foreign keys** that include `user_id` or `module_id`, for example
    `topics (module_id, user_id) → modules (id, user_id)` and `topics (parent_id, module_id) → topics (id, module_id)`.
  - So even code that forgets a check can't link a row to another user's data, or to another module.
- **Join tables** (`assessment_topics`, `session_topic_ratings`) carry `module_id` with composite FKs to both sides instead of `user_id`.
- **Guard test:** `tests/test_schema_guards.py` fails if a new table lacks `user_id` without being allow-listed.

## AI integration

- **Interface:** `LLMClient.complete(tier, messages, schema=None, stream=False)`. Features ask for a tier, and settings map
  each tier to a provider and model.
- **Structured output:** every saved AI result passes a Pydantic schema. It is retried once, then the job is marked for manual review.
- **AI suggests, code decides:** AI never changes the plan, deletes data or sends notifications.
- **Untrusted input:** uploaded documents are untrusted, and retrieved text is labelled as source material in prompts.
- **Free-tier privacy:** never send personal data (names, student numbers, emails, reflections). For COS330, the student's own
  `u23541475_*` submissions are excluded from AI processing.
- **Cost and rate controls:**
  - two tiers and per-feature token limits
  - each file is processed once (by hash), and practice items are cached
  - backoff on 429s, then fall back to Groq
  - `ai/budget.py`
- **Later:** a read-only MCP server (`get_modules`, `get_plan`, `get_weak_topics`, `search_materials`).

## Document pipeline

1. **Upload:** 50 MB limit and a type allow-list. Stored through the `Storage` interface (local folder in dev), with a hash recorded.
2. **Extract:** text per page or slide, with titles and speaker notes. Pages with no text layer are flagged as scanned.
3. **Chunk:** along page and slide boundaries, ~400–800 tokens, keeping the page reference.
4. **Index:** local embeddings plus `tsvector`.
5. **Understand (Flash):** topics per material, merged into the module tree; chunks linked by similarity, then user review.
6. **Past papers:** segment into questions with marks, map to topics, and classify type and difficulty. Code recomputes the profile.
7. **Search:** vector and keyword (top 20 each) → reciprocal rank fusion → module filter → current-topic boost → top 8 cited as [S1]–[S8].

## Camera and microphone (Phase 7 / 3)

- **Capture:** `getUserMedia` at 640×480. Face at ~5 fps and pose at ~1 fps in a Web Worker, slowed on weak laptops.
- **`signals.ts`** (pure functions):
  - presence
  - head yaw and pitch from the transformation matrix
  - blink edges with hysteresis
  - posture deviation from a 5 s calibration: face size, nose height vs the shoulder line, shoulder tilt
- **Modes:** "Screen" or "Desk/paper". In desk mode, looking down is normal.
- **What leaves the browser:** only per-minute summaries (presence ratio, head-away ratio, posture deviation, long eye closures).
- **`interventions.ts`:**
  - posture nudge after 3 min of drift, at most once every 15 min, never in the first 10 min
  - away for more than 5 min pauses the timer
  - breaks come from the plan
  - quiet mode
- **Microphone:** push-to-talk only. STT through an interface (the Web Speech API by default; the app says which vendor receives the audio).
  Answers stream back over SSE and are spoken sentence by sentence; speech should start within 2.5 s.
- **Risk:** background-tab throttling. Spike S1 tests a Worker + `MediaStreamTrackProcessor`, Document Picture-in-Picture and Tauri.

## Scheduling

- **Planner:** `services/planning/` is a pure function: (availability, assessments, workload, mastery, past-paper importance,
  block length) → plan blocks + a feasibility report.
  - Priority = importance × (1 − mastery) × urgency.
  - Each topic gets at least 2 spaced sessions and a final review where time allows.
  - Daily caps apply, and the next 24 h stay fixed.
- **Re-planning:** on a new assessment or material, a skipped or finished block, a mastery change, and nightly.
- **Timers:** live in the browser and are based on start and end timestamps, so a reload or throttling can't drift them. Every change is logged as a server event.
  - `src/session-engine/`: `timer.ts` holds pure functions of the events and an injected `now`: replay, live totals, focus/break
    cycle (default 50/10) and away detection. `engine.ts` drives it for the screen and owns no timers. A display tick only redraws.
  - **No drift from the server:** `fixtures/session-timelines.json` holds event logs with their expected totals. Both pytest
    (`timeline.py`) and vitest (`timer.ts`) run it.
  - **Offline:** events are queued in localStorage (`outbox.ts`) with their client UUIDs and keyed by the start event's id.
    The queue is flushed when the API answers. A resent event is a 200, so retries are safe, and a 409/422 is set aside for the screen.
  - **Away:** a last-active heartbeat is written every 15 s. A gap of more than 2 min while the clock runs (a page load or a
    tick after sleep) asks "keep that time, or stop the clock when you left?". Stopping posts a pause or end at the last-active
    time; during a break it first posts `break_end` at that time.
  - "Break due" is only shown. The engine never starts or ends a break by itself.
- **Reminders:** Web Push (VAPID + `pywebpush`), in-app notifications and a private ICS feed.

## Privacy and security

- **Camera and microphone:**
  - off by default and asked per session
  - a visible indicator and a one-click pause
  - both turn off automatically at the end of the session
- **Retention:** per-minute camera summaries for 90 days, then reduced to session totals. Deleting a material deletes its chunks and embeddings. Export and delete are available for everything.
- **Security:**
  - every query is scoped by `user_id`, with cross-user tests
  - keys are encrypted
  - AI endpoints are rate-limited
  - uploads are validated
- **Before multi-user launch:** a POPIA review.

## Local development

- **Prerequisites:** Git, `uv` (it fetches Python 3.12), Node LTS and Docker Desktop.
- **`npm run dev`:** starts Postgres, migrates, seeds, then runs uvicorn (:8000, reload) and Vite (:5173).
- **Same-origin API in development:** the web app calls `/api/*` on its own origin, and Vite proxies it to the API
  (`API_PROXY_TARGET`, default `http://localhost:8000`). The browser makes no cross-origin requests, so a
  browser-driving agent can test the UI as-is.
  - Setting `VITE_API_URL` makes the app call an API directly instead; the API keeps CORS for that case.
  - If the API is down, the proxy answers 502, and the health card shows "API: Not connected".
- **Secrets:** `apps/api/.env` and `apps/web/.env`, never committed. `.env.example` files document each setting.

## Testing and CI

- **Back end:** pytest against real Postgres (`studysensei_test`). The planner, mastery, metrics and budget get unit and Hypothesis property tests, and ingestion gets fixture files.
- **Front end:** Vitest + Testing Library. `timer.ts`, `signals.ts` and `interventions.ts` are tested against recorded landmark traces. Playwright covers the main flows (later).
- **AI quality:** `apps/api/evals/` runs before and after every prompt or model change.
- **CI** (`.github/workflows/ci.yml`), on PRs and pushes to main or rebuild:
  - **api:** ruff, ruff format, mypy (strict), alembic upgrade, pytest (pgvector service) and an OpenAPI-staleness check
  - **web:** eslint, prettier, tsc, vitest and vite build
- **Hosting from Phase 9:** an API and worker image on Fly.io/Railway/Hetzner, Supabase, and Cloudflare Pages for the web app.
