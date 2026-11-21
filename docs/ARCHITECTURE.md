# Architecture

The "how". Change it in the same PR as any change that alters it. Source: [the original plan](archive/PLAN.md) §3, updated by decision 0002.

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

| Area              | Choice                                                                                                                                                                                                                                                                                | Why                                                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Platform          | Web app (PWA), Chromium first                                                                                                                                                                                                                                                         | Easiest to polish; nothing to install; camera runs on-device. Tauri is the fallback if spike S1 fails ([0001](decisions/0001-web-rebuild.md)) |
| Front end         | React + TypeScript + Vite, Tailwind v4 + shadcn/ui, React Router, TanStack Query, Zustand                                                                                                                                                                                             | Largest ecosystem; no SSR needed                                                                                                              |
| Back end          | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg) + Alembic, `uv`                                                                                                                                                                                                      | Best document and ML libraries; Pydantic validates AI output                                                                                  |
| Database          | Postgres 16 + pgvector + built-in full-text search                                                                                                                                                                                                                                    | One service for relational data, vectors, keywords and jobs                                                                                   |
| Background jobs   | Worker polling a `jobs` table with `FOR UPDATE SKIP LOCKED` (decision 0004)                                                                                                                                                                                                           | No Redis; jobs survive restarts                                                                                                               |
| Embeddings        | Local `fastembed`, `BAAI/bge-small-en-v1.5` (384 dims, CPU)                                                                                                                                                                                                                           | Free, private, fast enough                                                                                                                    |
| LLM access        | Our own `LLMClient` with **one OpenAI-compatible adapter**                                                                                                                                                                                                                            | ~200 lines we control ([0002](decisions/0002-free-ai-providers.md))                                                                           |
| Models            | `smart`: Groq `openai/gpt-oss-120b` → `gemini-3.5-flash-lite` → `gemini-3.8-flash`; `bulk`: `gemini-3.5-flash-lite` → Groq `openai/gpt-oss-20b`; `vision` (any image): `gemini-3.5-flash-lite` → Groq `qwen/qwen3.8-27b` → `gemini-3.8-flash`; optional Ollama last in the text roles | Zero cost, ordered by free-tier daily limits and latency; roles live in config (see AI integration)                                           |
| PDF / Office      | `pypdfium2`, `python-pptx`, `python-docx`                                                                                                                                                                                                                                             | Permissive licences (PyMuPDF is AGPL; Docling pulls in PyTorch)                                                                               |
| Scanned pages     | Detect pages with no text layer; opt-in vision-LLM transcription                                                                                                                                                                                                                      | Tesseract handles maths and handwriting badly                                                                                                 |
| Spaced repetition | FSRS (`py-fsrs` / `ts-fsrs`)                                                                                                                                                                                                                                                          | Fewer reviews for the same retention                                                                                                          |
| Camera            | MediaPipe Tasks Vision (FaceLandmarker + blendshapes, PoseLandmarker lite) in a Web Worker                                                                                                                                                                                            | Free, private, proper blink and head-pose signals                                                                                             |
| Speech            | Push-to-talk; on-device Web Speech (`processLocally`) for STT, local `speechSynthesis` voices for TTS (0015)                                                                                                                                                                          | Zero cost, and audio never leaves the browser; upgradeable behind `listen()`                                                                  |
| Auth and hosting  | Single local user until Phase 9, then Supabase + one small container                                                                                                                                                                                                                  | One free tier covers DB, auth and storage                                                                                                     |

## Repository layout

```
apps/api/            FastAPI service (+ worker from Phase 2), one Python package `app`
  app/api/           routers (health; later modules, materials, sessions, plan, tutor, practice, profile)
  app/core/          config (pydantic-settings), db (async engine/session)
  app/models/        SQLAlchemy models (TimestampedBase: UUID id, created_at, updated_at)
  app/schemas/       Pydantic request/response + AI output schemas
  app/services/      search/ (chunking, embedding, indexing, search), planning/, mastery/, profile/, pastpapers/
  app/ai/            client.py (LLMClient), adapter.py (OpenAI-compatible), routes.py, budget.py, usage.py, sources.py, ping.py; later prompts/, retrieval.py
  app/jobs/          queue.py (enqueue, claim, retry), worker.py, kinds.py, tasks/ (extract_text, index_material, …)
  app/storage/       Storage interface + LocalStorage (data/materials), keys {user_id}/{sha256}
  alembic/           migrations
  tests/             pytest against real Postgres (studysensei_test)
  evals/             local evals against the dev DB (search, linking, topic_extraction); never in CI
  scripts/           export_openapi.py
apps/web/            React app
  src/app/           routes, layout, top navigation, providers
  src/features/      today/, modules/, session/, plan/, practice/, insights/, settings/
                     modules/materials/: MaterialsTab (upload + processing status), MaterialSearch,
                     PagesDialog (page list + MaterialViewer), MaterialViewer, pdf.ts (lazy pdf.js)
  src/vision/        camera.ts, vision.worker.ts, signals.ts, calibration.ts, rollup.ts   (Phase 7)
  src/voice/         stt.ts, tts.ts                                                       (Phase 3)
  src/session-engine/ timer.ts, interventions.ts                                         (Phase 1/7)
  src/lib/api/       openapi.json, generated schema.d.ts, typed client (openapi-fetch)
  src/ui/            design-system components (shadcn/ui restyled to docs/DESIGN.md; tokens in src/index.css)
apps/web/e2e/        Playwright specs
infra/db/init.sql    creates studysensei_test
docker-compose.yml   Postgres 16 + pgvector on host port 5433
scripts/dev.mjs      `npm run dev`: db → migrate → seed → api + job worker + web
```

Folders marked with a phase are created when that phase starts.

## API contract

FastAPI generates OpenAPI. `npm run gen:api` writes `apps/web/src/lib/api/openapi.json` and regenerates `schema.d.ts`, and
the web app calls the API through the typed `openapi-fetch` client. CI fails if the committed schema is stale.

`GET /health` returns `{status, api, database, database_error}`: 200 when Postgres answers `SELECT 1` within 2 s, otherwise 503.

**Endpoints so far:**

| Area        | Routes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Modules     | `GET/POST /modules`, `GET/PATCH/DELETE /modules/{id}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Topics | `GET /modules/{id}/topics` (nested tree; each node has `linked_pages`, `confidence` and `workload`: `{minutes, source: yours/estimated/none, slide_pages, text_pages}`), `POST /modules/{id}/topics`, `PATCH/DELETE /topics/{id}`, `POST /topics/{id}/move` `{parent_id, position}` (any edit makes an AI topic `source = user`), `PATCH /topics/{id}/planning` `{confidence?, estimated_minutes?}` (null clears either) |
| Topic maps  | `GET /modules/{id}/topic-map` (eligible / analysed / pending / failed materials, `merging`, `waiting_until`, `last_error` (only a failure newer than the latest successful merge), `merged_at`), `POST /modules/{id}/topic-map/build` (decision 0006); `GET /modules/{id}/topic-map/materials` (each eligible material: `analysed` / `failed` with `error` / `waiting`), `POST /materials/{id}/topics/retry` (a new run; 422 if its topics aren't found), `DELETE /modules/{id}/ai-topics` (`{deleted}`; decision 0007). The status also has `review` (kept, renamed, merged, dismissed, unreviewed). Review (decision 0009): `POST /topics/{id}/keep`, `POST /topics/{id}/merge-into` (`{target_id}`; 422 for itself, a subtopic or another module), `POST /topics/{id}/dismiss` (`{dismissed}`; 422 unless still AI), `POST /modules/{id}/topics/keep-all` (`{kept}`), `GET /modules/{id}/dismissed-topics`, `POST /dismissed-topics/{id}/restore`, `GET /topics/{id}/pages` (linked pages by material: number, label, `pages` or `similarity` with score), `DELETE /topics/{id}/pages/{material_id}/{page}` (unlink, remembered)                                                                                                                                                                          |
| Assessments | `GET/POST /modules/{id}/assessments`, `GET /assessments?status=` (all modules), `GET/PATCH/DELETE /assessments/{id}` (responses include `topic_ids`; sending `topic_ids` replaces the whole set)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Tasks       | `GET/POST /modules/{id}/tasks`, `GET /tasks?status=` (all modules), `GET/PATCH/DELETE /tasks/{id}` (`status: "done"` sets `completed_at`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Sessions    | `POST /sessions`, `GET /sessions/active`, `GET/DELETE /sessions/{id}`, `POST /sessions/{id}/events`, `PUT /sessions/{id}/reflection`, `GET /modules/{id}/sessions?limit=&offset=` (a page `{items, total, limit, offset}`: the open session first, then newest first; limit 1–100, default 20), `GET /modules/{id}/sessions/summary?week_start=` (session count and active seconds, all time and since `week_start`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Planning | `GET/PATCH /planning/settings` (`{timezone, daily_study_cap_minutes, reminder_minutes}`: IANA, 15-1,440, and 5, 10, 15, 30 or null for off), `GET/POST /availability/rules`, `PATCH/DELETE /availability/rules/{id}` (`{weekday, start, end}` as "HH:MM", "24:00" for midnight; 409 on an overlap that weekday), `GET /availability/exceptions?from=&to=`, `POST /availability/exceptions`, `PATCH/DELETE /availability/exceptions/{id}` (`{date, unavailable, windows, note}`; 409 for a second one on a date), `GET /availability?from=&to=` (at most 62 local dates: each with `source` rules/exception/unavailable, UTC `intervals`, `free_minutes`, `available_minutes` after the cap; totals and `weekly_minutes_from_rules`) |
| Plan | `GET /plan/preview?days=` (computed, nothing stored), `GET /plan?from=&to=` (the current version, its blocks in the range and the history: done, skipped and missed blocks of any version; per block `start`/`end` (a done block's are its session's measured times; ADR 0023), `planned_start`/`planned_end`, `status` (missed derived on read), `fixed`, `pinned`, `linked_session_id`, `session_minutes`, `actions {start, skip, move}`; `replan_pending`; creates version 1 when there's none), `GET /plan/next` (the next planned block with its actions, or null), `POST /plan/blocks/{id}/skip` (409 "Its session is still open." with an open linked session), `POST /plan/blocks/{id}/move` `{start}` (5-minute grid; 422 with one sentence for a rule problem; 409 for a block that started, has a session or isn't current), `POST /plan/replan`. `POST /sessions` takes `plan_block_id` |
| Reminders | `GET /push/config` (`{enabled, public_key}`: enabled when the VAPID keys are set), `POST /push/subscriptions` (`{endpoint (https), keys {p256dh, auth}, label}`: upserts by endpoint for this user, 201 new or 200), `GET /push/subscriptions` (`id, label, created_at, last_success_at`; never the endpoint), `DELETE /push/subscriptions/{id}`, `POST /push/test` ("Reminders work" to each device now: `{devices: [{id, label, outcome: sent/failed/removed}]}`; 409 when push is disabled) |
| Calendar | `POST /calendar/feed` (201: `{url, created_at}`, the URL shown once; again resets it and the old link stops working), `GET /calendar/feed` (`{exists, created_at, last_fetched_at}`, never the token), `DELETE /calendar/feed`, `GET /calendar/{token}.ics` (**no sign-in**: the token is the credential; that user's plan only, 404 for an unknown token; `text/calendar; charset=utf-8`, `Cache-Control: private, max-age=300`; records `last_fetched_at`; must stay outside any future auth middleware, ADR 0024), `GET /calendar/plan.ics` (the same file for the signed-in user, as a download) |
| AI          | `GET /ai/status`: per provider whether it's configured (`key_set` is yes/no only), each role's models in order, and per model `used_today` / `daily_budget` / `resets_at` for the current user                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| AI          | `POST /ai/ping` (no body): tests every configured model at once, one short request each (30 s limit each), logged in `ai_usage` as purpose `ping` against the caller. One result per model: `status` `ok` (`latency_ms`), `failed` (`error`: the provider's own text, never a key) or `skipped` (daily budget used up, so not called; `resets_at`), plus `in_models_list` (null with `models_list_error` when the provider's `/models` failed). No provider configured → `results: []`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Tutor       | `GET /modules/{id}/tutor/conversations?study_session_id=` (newest first, each with its messages; another user's session ID gives `[]`; the panel restores a session's conversation with it), `POST /modules/{id}/tutor/conversations` (`{study_session_id?, topic_id?}`, 201; both must be in the module; without a topic the session's is used), `GET /conversations/{id}` (messages oldest first; each answer has its `model`, `status`, `first_token_ms`, `total_ms`, `unknown_citations` and `sources` with `label`, `rank`, material, page, `cited`), `POST /conversations/{id}/messages` (`{question, mode}`, mode `answer` / `explain_differently` / `example`) → `text/event-stream`, below; `POST /conversations/{id}/quiz` (no body, 201: the stored quiz answer, `failed` with a readable `text` if the AI's quiz couldn't be used; 422 before any answer; 503 with `Retry-After` when the AI is busy), `PATCH /messages/{id}/quiz-answers` (`{answers: [0–3 or null, …]}`, one per question; 422 if it isn't a quiz or the count differs), `PATCH /messages/{id}/voice-timing` (`{voice_latency_ms, transcript_ms, first_token_ms, first_sentence_ms}`, each 0–600,000 ms from releasing push-to-talk; 422 unless it's an answer; returned on messages as `voice_latency_ms` and `voice_timing`) |
| Materials   | `POST /modules/{id}/materials` (multipart: `file`, `kind`, `title?`, `allow_ai`; 413 over 50 MB, 415 wrong type, 409 same file in the module), `GET /modules/{id}/materials`, `GET/PATCH/DELETE /materials/{id}` (PATCH: title, kind, allow_ai), `POST /materials/{id}/retry` (failed only), `GET /materials/{id}/pages` (page number, title, char count, is_scanned), `GET /materials/{id}/pages/{n}` (adds the text), `GET /materials/{id}/file` (the stored original, streamed through `Storage`: its own `Content-Type`, `Content-Disposition: inline` with the RFC 5987 filename, `X-Content-Type-Options: nosniff`, `ETag` = the sha256 with `Cache-Control: private, max-age=31536000, immutable`, and 304 for a matching `If-None-Match`; 404 for another user's material or a missing blob)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

Notes on these endpoints:

- A module's own lists live under `/modules/{id}/…` and return 404 if the module isn't yours. The top-level
  `/assessments` and `/tasks` are cross-module lists (used by Today); repeat `status` to filter, e.g.
  `?status=todo&status=in_progress`.
- Dates (`due_at`) must include a timezone; a bare local time is a 422.
- Lists come soonest first, with undated items last.
- List filters with someone else's ID return `[]`, exactly like a non-existent ID.

**The tutor's stream** (decision 0013): `POST /conversations/{id}/messages` answers 404 (another user's or a missing
conversation) or 422 before the stream opens. A dependency finds the conversation, runs retrieval and stores the
question first. Then it streams these events, in order:

| Event     | Data                                                                                                      | When                                                                                                       |
| --------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `sources` | `{sources: [{label, material_id, material_title, page_number, page_title}]}`                              | First, before any text (may be empty)                                                                      |
| `delta`   | `{text}`                                                                                                  | Each piece of the answer (never the model's thinking)                                                      |
| `done`    | `{message_id, status (complete or truncated), model, first_token_ms, total_ms, cited, unknown_citations}` | Last, when an answer was given                                                                             |
| `error`   | `{message_id, message, retry_at}`                                                                         | Last, when it wasn't: `retry_at` is set when the AI is busy or out of quota, null when retrying won't help |

- The events are typed in the OpenAPI (an SSE item schema over `SourcesEvent | DeltaEvent | DoneEvent | ErrorEvent`).
  FastAPI adds keep-alive comments.
- If the client disconnects, the provider's stream is stopped and the partial answer is stored as `stopped`.

Topic `position` is the index among siblings. New topics append, and moves/deletes renumber the siblings to 0..n-1.

**Errors** always use `{"detail": ...}`:

| Status | Meaning                                                                                                                                           | `detail`                                            |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| 404    | Not found, **or another user's row** (deliberately indistinguishable)                                                                             | a string                                            |
| 409    | Uniqueness conflict, e.g. a duplicate module code (case-insensitive)                                                                              | a string                                            |
| 422    | Invalid input: Pydantic validation, an explicit `null` for a required field, or a disallowed operation (e.g. moving a topic into its own subtree) | a list of issues for validation, a string otherwise |
| 503    | `AIUnavailable`: no provider configured, or every model rate-limited or out of budget; `Retry-After` when known                                   | a string                                            |

PATCH bodies only change the fields sent. `null` is accepted only for clearable fields (each `*Update` schema's `nullable` set).

## Data model

Every table has:

- a UUID primary key
- `user_id` (except child tables reached through a parent)
- `created_at` and `updated_at`

Derived tables can always be rebuilt from source tables.

| Area                | Tables                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| People and settings | `users`, `ai_credentials`, `consents`, `push_subscriptions`, `reminders_sent`, `calendar_feeds`                                                                                                                                                                                                                                                                                                                                                                                                                             | Keys Fernet-encrypted; consent per feature with timestamps                                                                                                                                                                                                                                                                                                                                                                                      |
| Academic structure  | `modules`, `topics` (tree via `parent_id`), `assessments`, `assessment_topics`, `tasks`                                                                                                                                                                                                                                                                                                                                                                                                 | `topics.source` is `ai` or `user`; user edits never overwritten                                                                                                                                                                                                                                                                                                                                                                                 |
| Materials           | `materials`, `material_pages` (text per page, `is_scanned`), `chunks` (one page each: page number, position, text, token count, `embedding vector(384)`, generated `tsv tsvector`), `chunk_topics` (chunk, topic, score, method `pages`/`similarity`)                                                                                                                                                                                                                                   | `materials.kind`: slides, notes, study_guide, tutorial, past_paper, test, assignment, outline, other; `status`, `error`, `page_count`, `allow_ai`; `UNIQUE (module_id, sha256)`                                                                                                                                                                                                                                                                 |
| Topic maps          | `topic_proposals` (one per material: validated AI JSON + provider and model), `topic_pages` (pages each topic was drawn from), `topic_reviews` (what the student did with each AI topic; outlives it), `topic_unlinks` (pages unlinked from a topic)                                                                                                                                                                                                                                    | Decisions 0006, 0009                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Past papers         | `past_questions`, `past_question_topics`                                                                                                                                                                                                                                                                                                                                                                                                                                                | Profile computed by queries, never stored as AI output                                                                                                                                                                                                                                                                                                                                                                                          |
| Planning | `availability_rules` (weekday 0 is Monday, `start_minute`/`end_minute` after local midnight, never across it; overlaps refused per user and weekday by an exclusion constraint), `availability_exceptions` (one per user and date: `unavailable`, or `windows` as JSONB minutes, and a `note`), `plan_versions` (number per user, trigger, summary, generated/checked, the report as JSONB), `plan_blocks` (a version's blocks with texts, status `planned`/`done`/`skipped`/`missed`, `fixed`; composite FKs on `user_id`); on `users`: `timezone` (IANA) and `daily_study_cap_minutes`; on `topics`: `estimated_minutes` (the student's figure) and `confidence` (1-5, self-rated) |
| Sessions            | `study_sessions`, `session_events`, `session_minutes`                                                                                                                                                                                                                                                                                                                                                                                                                                   | No images or audio, ever                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Practice            | `practice_items`, `reviews` (grade + FSRS state)                                                                                                                                                                                                                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Derived             | `topic_mastery`, `profile_metrics` (value, sample size, label), `recommendations`                                                                                                                                                                                                                                                                                                                                                                                                       | Rebuilt nightly and after each session                                                                                                                                                                                                                                                                                                                                                                                                          |
| Tutor               | `conversations` (module, optional study session and topic), `messages` (`position` in the conversation, role `user`/`assistant`, mode, text, status `complete`/`truncated`/`failed`/`stopped`, model, `first_token_ms`, `total_ms`, `unknown_citations`), `message_sources` (label S1–S8, rank, material, page, titles copied, `chunk_id`, `cited`); `messages.quiz` and `quiz_answers` (JSONB, 0019); `messages.voice_latency_ms` and `voice_timing` (JSONB parts, answers only, 0020) | Migrations 0017–0020. Every table has `user_id` and composite FKs: a conversation's session and topic must be in its module. **Deleting a study session deletes its conversation, messages and sources** (0019; it was SET NULL, which left an unreachable conversation); deleting the topic keeps the conversation without it. A source's material is the same user's (set to null if deleted, titles kept). The prompt itself is never stored |
| AI                  | `ai_usage`                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Usage drives budget and rate-limit handling; outcome `stopped` (0017) is a stream the student stopped                                                                                                                                                                                                                                                                                                                                           |
| System              | `jobs` (kind, payload, status, attempts, run_after, error)                                                                                                                                                                                                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

**Built so far:**

- `users` + the `vector` extension (migration 0001)
- `modules`, `topics`, `assessments`, `assessment_topics`, `tasks` (0002)
- `study_sessions`, `session_events`, `session_topic_ratings` (0003)
- 0004 is data only: existing module colours mapped to the design-system swatches (nearest hue)
- `chunks` (0007), with a GIN index on `tsv` and no vector index (decision 0005)
- `ai_usage` (0008): user, provider, model, role, purpose, input/output tokens, latency, outcome (`ok`, `rate_limited`,
  `error`, `invalid_json`, and `timeout` from 0009). Never prompt or reply text. Roles `vision` (0010) and `long` (0011).
  0012 adds `job_id` (the job that made the call), `detail` (why it failed: HTTP status and provider message, or
  what didn't validate; ≤ 300 characters) and the `truncated` outcome. 0013 adds `overloaded` (a 503, turned away
  before running) and `refused` (the model declined the content; decision 0008). 0014 adds `too_large` (a 413).
- `topic_reviews` and `topic_unlinks` (0014; decision 0009). `topic_reviews.target_id` is a single-column FK with
  `ON DELETE SET NULL` (a composite one would null `module_id`); `topic_id` has no FK, as the row outlives it.
- `topic_proposals`, `topic_pages`, `chunk_topics` (0011), plus `UNIQUE (id, module_id)` on `chunks`; the migration
  queues `extract_topics` for every eligible indexed material.
- `availability_rules`, `availability_exceptions`, `users.timezone` and `daily_study_cap_minutes`, and
  `topics.estimated_minutes` and `confidence` (0021). It enables `btree_gist` for the rules' exclusion constraint.
- `push_subscriptions` (`UNIQUE (id, user_id)`, `UNIQUE (user_id, endpoint)`, https endpoints only, `failures >= 0`), `reminders_sent` (`UNIQUE (user_id, slot_key)`; the slot is sha256 of start, end, assessment and topic), `calendar_feeds` (`UNIQUE (user_id)`, `UNIQUE (token_hash)`; only the token's sha256), and `users.reminder_minutes` (null, 5, 10, 15 or 30; default 10) (0024; decision 0024).
- `plan_blocks.pinned` and the `move` trigger (0023; decision 0022).
- `plan_versions` and `plan_blocks` (0022; decision 0021): `UNIQUE (id, user_id)` on both, `UNIQUE (user_id, number)`,
  an index on `plan_blocks (user_id, start_at)`, composite FKs from blocks to their version, module, assessment and
  topic (deletes cascade); `study_sessions (plan_block_id, user_id) → plan_blocks` with `ON DELETE SET NULL
  (plan_block_id)`; and `uq_jobs_one_queued_replan`, a partial unique index on `jobs (user_id)` for queued re-plans.

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
- **History:** the module's Sessions tab pages through `GET /modules/{id}/sessions`. "This week" is the client's local
  Monday 00:00, sent as an aware `week_start`; a session counts in the week it started. Study time is active time only
  (breaks aren't study time), and an open session counts up to its last event on the server.
- `plan_block_id` is the planned block the session is for (0022): the same user's, set to null if the block is deleted.

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

Decision 0002. Everything goes through `app/ai/`; nothing else talks to a provider.

- **One adapter:** `adapter.py` speaks the OpenAI chat-completions API over httpx (`POST {base}/chat/completions`,
  `GET {base}/models`) for every provider:
  - Gemini (primary): `https://generativelanguage.googleapis.com/v1beta/openai/`, `GEMINI_API_KEY`
  - Groq (fallback): `https://api.groq.com/openai/v1`, `GROQ_API_KEY`
  - Ollama (optional): `http://localhost:11434/v1`, no key, on only when `OLLAMA_MODEL` is set (then last in every role, no budget)
- **Roles, in config** (`AI_SMART`, `AI_BULK`, `AI_VISION` in `app/core/config.py`): ordered lists of routes, each
  a `"provider/model"` plus a `reasoning_effort`:

  | Role     | Used for                                                             | Models, in order                                                                      | Thinking  |
  | -------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------- |
  | `smart`  | the tutor                                                            | `groq/openai/gpt-oss-120b`, `gemini/gemini-3.5-flash-lite`, `gemini/gemini-3.8-flash` | `low`     |
  | `bulk`   | classification, tagging                                              | `gemini/gemini-3.5-flash-lite` (`minimal`), `groq/openai/gpt-oss-20b` (`low`)         | as listed |
  | `vision` | any request with an image: scanned pages, figure slides              | `gemini/gemini-3.5-flash-lite`, `groq/qwen/qwen3.8-27b`, `gemini/gemini-3.8-flash`    | `low`     |
  | `long`   | whole documents in one prompt: topic extraction and the module merge | `gemini/gemini-3.5-flash-lite`, `gemini/gemini-3.8-flash`, `groq/openai/gpt-oss-120b` | `low`     |

  **Why this order** (re-ranked 2026-11-17 after real pings):
  - `gemini-3.8-flash` allows only ~20 requests a day and timed out at 30 s twice, at its default level and at `low`.
    It can't carry the tutor or topic maps, so it's the last resort in `smart` and `vision`.
  - `gemini-3.5-flash-lite` answers in 1–10 s and allows ~500 a day.
  - Groq's gpt-oss allows ~1,000 a day and is fast, so `gpt-oss-120b` leads `smart`.

  **Images:** a request with an image always uses `vision`, whatever role it asked for, and its usage rows say
  `vision`. Every model there accepts images, per the provider docs: both Gemini model pages list image input, and
  Groq's Qwen takes up to 3 images per request (2,048 tokens each). Groq's gpt-oss is text-only. Ollama isn't added
  to `vision`, since a local model may not read images.

- **Thinking level:** Gemini 3 models always think, at the model's own default level unless `reasoning_effort` is
  sent, and that default can make even a one-word reply slow. Each route's level (`minimal`, `low`, `medium`, `high`,
  or empty to send nothing) is checked against the levels its model accepts (`AI_REASONING_EFFORTS`, from each
  provider's docs). A level the model lacks is raised to its lowest supported level at or above it
  (`routes.wire_effort`), and a model that isn't listed (Ollama) is sent none:

  | Model                                            | Levels                                                         | Default        |
  | ------------------------------------------------ | -------------------------------------------------------------- | -------------- |
  | `gemini-3.8-flash`                               | `low`, `medium`, `high` (no `minimal`: asking for it is a 400) | `medium`       |
  | `gemini-3.5-flash-lite`                          | `minimal`, `low`, `medium`, `high`                             | `minimal`      |
  | Groq `openai/gpt-oss-120b`, `openai/gpt-oss-20b` | `low`, `medium`, `high`                                        | not documented |
  | Groq `qwen/qwen3.8-27b`                          | `low`, `medium`, `high` (also its own `none` / `default`)      | not documented |

  A call can ask for more with `complete_text(…, reasoning_effort="high")`. The ping always uses `minimal`.

- **Free-tier limits and budgets** (`AI_DAILY_BUDGET`, requests per day, about 10 % under the limit). Google no longer
  publishes free-tier numbers. These are the per-project quotas that AI Studio and 429 replies reported in Sept–Nov 2026.
  Check yours at aistudio.google.com/rate-limit and console.groq.com/settings/limits.

  | Model                      | Free tier                                     | Budget | Resets                 | Images |
  | -------------------------- | --------------------------------------------- | ------ | ---------------------- | ------ |
  | `gemini-3.8-flash`         | 5 RPM, 20 RPD                                 | 18     | midnight Pacific       | yes    |
  | `gemini-3.5-flash-lite`    | 15 RPM, 500 RPD                               | 450    | midnight Pacific       | yes    |
  | Groq `openai/gpt-oss-120b` | 30 RPM, 1K RPD, 8K TPM, 200K TPD              | 900    | midnight UTC (assumed) | no     |
  | Groq `openai/gpt-oss-20b`  | 30 RPM, 1K RPD, 8K TPM, 200K TPD              | 900    | midnight UTC (assumed) | no     |
  | Groq `qwen/qwen3.8-27b`    | 30 RPM, 1K RPD, 8K TPM (3 images per request) | 900    | midnight UTC (assumed) | yes    |

  Groq's Llama models left the free tier on 16 Aug 2026. Groq's limits page shows only its Developer-plan base table
  (the same 1K RPD), and Google publishes no free-tier numbers, so the budgets are unchanged from the first measurements.
  With gpt-oss leading `smart`, its 200K tokens per day may run out before its 1K requests do: topic maps send long
  prompts. Budgets count requests only, so a token limit shows up as 429s that fall through to Flash-Lite.

- **Interface** (`client.py`): `complete_text(role, messages, *, purpose, user_id, reasoning_effort=None)` and
  `complete_json(role, messages, Schema, *, purpose, user_id, reasoning_effort=None)`. Messages are `system()` / `user(text, *images)`. An
  image (a scanned page) is sent inline as a data URL, and the request goes to the `vision` role.
- **Structured output:** `complete_json` asks for a JSON object (the schema goes in the system prompt, with
  `response_format: json_object`) and validates it with Pydantic (a Markdown fence is tolerated). If it fails, one
  repair turn is sent with the validation errors. A second failure raises `AIInvalidOutput`, and the caller marks the
  item for manual review.
- **Routing per request:** the client walks the role's models in order. It skips a model whose provider has no key,
  that can't read the images, that is cooling down after a 429/5xx, or whose daily budget is spent.
  - **Pacing:** each model has a requests-per-minute limit (`AI_REQUESTS_PER_MINUTE`, the free tier less a margin:
    Flash-Lite 12, 3.8 Flash 4, Groq 25). A request waits its turn in a one-minute window (per process) instead of
    collecting 429s.
  - **Timeouts:** 10 s to connect (`AI_CONNECT_TIMEOUT_SECONDS`) and 90 s to wait for the reply
    (`AI_READ_TIMEOUT_SECONDS`). A timeout is logged as `timeout` and counts against the budget (the provider may
    have answered after we stopped waiting).
  - **What moves on to the next model** (decisions 0007, 0008): only "this model can't take it now". That means a
    429, a 503 ("high demand", logged `overloaded`), a timeout, a lost connection, or a 413 (too large for that
    model's limits, logged `too_large`; the model isn't cooled down, as a smaller request may fit). Also a content refusal: `finish_reason` `content_filter` / `SAFETY` / `PROHIBITED_CONTENT` (and
    similar) or an empty reply, logged `refused`. It spends no repair and doesn't cool the model down; if every model
    refuses, `AIRefused` fails the job with each model's reason.
    - A 429 or 5xx is first retried once on the same model when the wait (the `Retry-After` header or HTTP date,
      Gemini's `retryDelay`, or 2 s × 2ⁿ backoff, plus jitter) is at most `AI_MAX_WAIT_SECONDS` (20 s). Otherwise
      the model cools down (at least a minute).
    - Any other persistent 5xx (500, 502, 504) raises `AIUnavailable` (the job waits).
    - Any other refusal (400, 401, 404…) raises `AIRequestFailed` with the provider's message, and the job fails at
      once.
    - Invalid output is repaired once at most and never moves to another model.
  - **Cut off:** a reply with `finish_reason` `length` raises `AITruncated` (logged `truncated`, not repaired).
  - **Call budgets:** a caller can pass a `CallBudget` (calls and repairs for one unit of work, every fallback
    included). Topic jobs count their calls across retries from `ai_usage.job_id`. Requests turned away before
    running (429, 503, 413) don't use that cap; they have their own wider one (`TOPIC_MAX_TURNED_AWAY`, 20) so an
    outage still ends (decisions 0008, 0009).
  - **Error text:** a failed request reads like `gemini: HTTP 400: Thinking level MINIMAL is not supported…`. Only the
    body's `error.message` is used, trimmed to 300 characters, never the request or headers.
  - **Budgets** (`budget.py`): the user's `ai_usage` rows for that model since the provider's last local midnight
    (`AI_QUOTA_TIMEZONE`). They count `ok`, `error`, `invalid_json`, `timeout`, `truncated` and `refused`. A 429,
    503 or 413 isn't counted: it was turned away before running (decisions 0007–0009).
  - **All out:** `AIUnavailable(retry_at=…)`, set to the earliest cooldown end or budget reset. The worker reschedules
    the job for then without using an attempt (`queue.reschedule`), and the API answers 503 with `Retry-After`. With no
    provider configured, `retry_at` is None: jobs fail with "AI isn't set up yet…", and nothing crashes.
- **Usage:** every request writes an `ai_usage` row in its own session, including retries and failures, so a job that
  rolls back still leaves its calls on record. Keys are `SecretStr` and sent only in the `Authorization` header. They
  are never logged, stored or returned (`/ai/status` says yes or no).
- **Privacy** (free-tier prompts may be used by the provider):
  - Course text reaches prompts only through `app/ai/sources.py` (`chunks_for_prompt`, `material_pages_for_prompt`),
    whose queries filter on `materials.allow_ai = true` and `user_id`. It hands out the material title and page text,
    never the original file name (which can hold a student number).
  - The client never looks the user up: `user_id` is only for usage rows and budgets. No names, emails, student
    numbers or reflections go in prompts.
  - For COS330, the student turns `allow_ai` off on their own submissions.
- **Checking keys:** `app/ai/ping.py` `ping_routes` sends "Reply with the single word: pong" to every configured model
  at once, at `minimal` effort, and returns one structured `PingOutcome` per model. A model whose daily budget is used
  up isn't called (`skipped`, with its reset time). Each model gets 30 s in total, so a slow one can't hold up the
  rest, and it also checks each model ID against the provider's `/models` list. Two front ends share it:
  `uv run python -m app.ai.ping` prints `→ provider/model …` then `ok` with the latency and reply, `FAIL` with the
  reason, or `skipped`; and `POST /ai/ping` behind the Settings page's "Test keys" button.
- **Settings page** (`features/settings/`): providers as "Key set" / "No key" (Ollama: model set or not), each role's
  models in order with what uses it, today's usage per model as a meter (count measured, budget estimated, reset in
  local time), "Test keys", and the privacy note; and Study time (Phase 4, below). Keys and routes are edited only in `apps/api/.env` until Phase 9.
- **Tests never call a provider:** `tests/conftest.py` blanks the key variables (the environment beats `.env`) and
  installs a client whose transport fails any request. AI tests script replies with `FakeLLM` (`tests/fakes.py`).
- **AI suggests, code decides:** AI never changes the plan, deletes data or sends notifications.
- **Untrusted input:** uploaded documents are untrusted, and retrieved text is labelled as source material in prompts.
- **Streaming** (decision 0013): `stream_text(role, messages, *, purpose, user_id, interactive=True)` yields
  `TextDelta` (answer text and the model writing it) and then one `StreamDone`.
  - The routes, budgets, pacing, timeouts and effort levels are `complete_text`'s, with one `ai_usage` row per
    attempt.
  - **Fallback only before the first answer token** (thinking deltas don't count). After it, a failure raises
    `AIStreamFailed`, so two models are never spliced.
  - **Interactive calls never wait:** a 429 or 503 moves straight on, and another 5xx is `AIUnavailable` at once.
    Background calls keep 0007's short retry. `_after_failure` holds both rules.
  - `finish_reason` "length" ends normally, marked truncated. Closing the iterator closes the provider's stream
    (outcome `stopped`).
- **The tutor turn** (`app/services/tutor/turn.py`, `conversations.py`):
  - **History:** the last 2 answered exchanges (`complete` or `truncated`) go in as chat turns, inside
    `TUTOR_CONTEXT_MAX_TOKENS`. The sources take what they need first, then the oldest exchange is dropped until
    the rest fits. An earlier answer's `[Sn]` labels are stripped, because they pointed at that turn's sources.
  - **Citations** are parsed when the stream ends. Both `[S1]`, `[S2, S4]` and gpt-oss's full-width `【S1】` count.
    A label that wasn't given (`S9`) is kept out of the citations and listed in `unknown_citations`, and the text is
    never rewritten.
  - **Timings** are measured from receiving the question.
  - **Interactive JSON repairs** (decision 0014): the repair goes to the model that wrote the reply. If that
    model turns it away (429, 503, 413, a timeout, a cooldown or its budget), the next models get the original
    prompt afresh, so one model's reply is never handed to another. A 5xx still fails at once, and background
    calls keep their short wait.
  - **"Quiz me"** (`app/services/tutor/quiz.py`, not streamed):
    - It's made from the last answer's sources only (`reuse_sources`, the same passages and labels), plus the question
      that answer was for. `complete_json` validates the reply against `Quiz`, with one repair. It's interactive: a
      busy model is skipped, not waited for.
    - **Schema** (`app/schemas/tutor.py`): `Quiz.questions`, 1–6 accepted, each with:
      - `prompt`;
      - exactly 4 `options`;
      - `correct`, the option's index 0–3;
      - a one-line `explanation` citing like [S1];
      - `sources`: labels, with "[S1]", "【S1】" and "s1" all normalised to "S1".
    - **Code keeps** a question only if all its labels are among the answer's sources, and keeps at most 3. Fewer
      are shown as they are, and the panel says so. None left is a `failed` answer saying why.
    - **Stored** in `messages.quiz` (validated) with `quiz_answers` all null. The question "Quiz me" and the answer are
      a turn like any other, but **not history** for the next question.
    - **Graded by code**, in the panel and in `grade()`, never by the model. No mastery or plan changes (Phase 5).
  - **Prompt rules from the live review:**
    - Prefer lists, and use tables only of at most 3 columns (answers are read on phones).
    - Always write citations in brackets, tables included.
    - In a quiz, check each wrong option against the sources.
    - The parser stays strict: only `[S1]` and `【S1】` count.
  - **Follow-ups** (19 Nov review of #36):
    - `explain_differently`, `example` and `quiz` are given the last answer's sources again, with the same labels, so
      their citations match. `message_sources.chunk_id` (migration 0018) keeps the exact passage; after a re-index,
      the page's first chunk is used instead. A material whose AI was turned off since drops out, and the others keep
      their labels.
    - A new question in answer mode, once the conversation has one, runs a second search on the previous question
      and this one together, fused with the first by RRF. On COS330's three eval follow-ups, an acceptable page was
      in the 8 for 3 of 3, against 2 of 3 searched alone.
  - **Startup:** the API (in a background thread from its lifespan, so `/health` answers at once) and the worker
    load the embedding model as they start (`PRELOAD_EMBEDDER`), so the first question after a start is as quick
    as the rest.
- **CLI:** `uv run python -m app.tutor.ask --module COS330 "question" [--topic NAME] [--mode …] [--dry-run]` runs the
  same service. It prints the sources, streams the answer, then the model, time to first token, cited sources and AI
  calls. `--dry-run` writes nothing: the session is read-only in Postgres, and usage is kept in memory (today's
  earlier calls still count toward budgets).
- **Later:** per-feature token limits, cached practice items, user-supplied keys (`ai_credentials`, Phase 9) and a
  read-only MCP server (`get_modules`, `get_plan`, `get_weak_topics`, `search_materials`).

## Document pipeline

1. **Upload:** 50 MB limit and a type allow-list checked by content. Stored through the `Storage` interface (local folder
   in dev) under `{user_id}/{sha256}`, so a re-upload is detected and a file shared by two modules is stored once
   (decision 0004). The material and its first job are created in one transaction; the worker extracts it, then indexes it, and only then marks it ready.
   - **Status:** `uploaded` → `processing` → `ready`, or `failed` with a readable reason once retries run out
     (retrying meanwhile).
   - **`allow_ai`:** each material has this flag (default on); AI steps skip materials where it is off.
2. **Extract** (`extract_text` job, `app/services/extraction.py`): text per page into `material_pages`.
   - **Readers:**
     - PDF pages (pypdfium2)
     - PPTX slides: title, body text and tables, then "Speaker notes:"; one page per slide
     - DOCX, MD and TXT: split at headings, or at a paragraph boundary after about 800 words; DOCX tables as "a | b" rows
     - PNG/JPG: one empty page
   - **Scanned:** a page with fewer than 20 non-space characters; `materials.scanned_page_count` counts them for the later
     vision step.
   - **Failures:** damaged or password-protected files fail at once (`JobError(retry=False)`) with a readable reason;
     library errors never reach the student.
   - **Re-runs:** re-extracting replaces a material's pages (and, by cascade, its chunks).
   - **Next:** a successful extraction queues `index_material`; the material stays `processing` until it finishes.
3. **Chunk** (`index_material` job, `app/services/search/chunking.py`, decision 0005): never across two pages, so every
   result points at one page or slide.
   - **Size:** at most 400 tokens, counted with the embedding model's own tokenizer (bge-small-en-v1.5 reads 512 tokens
     at most, so the earlier "400–800" would have been cut off).
   - **Splitting:** a page that fits is one chunk. A longer page splits at paragraphs, then lines, sentences and words,
     only as far as needed, with ~50 tokens of overlap (from a sentence start when one fits).
   - **Scanned pages** are skipped until the vision step reads them.
   - **Stored text** is exactly the page's; the **embedded text** leads with "material · page title".
4. **Index:** fastembed `BAAI/bge-small-en-v1.5` on the CPU (`passage_embed` for chunks, `query_embed` for searches),
   loaded once per process and cached in `data/models` (the first run downloads it), plus a generated english
   `tsvector` with a GIN index. Embedding is local, so it runs whatever `allow_ai` says.
5. **Understand** (decision 0006, `long` role):
   - **`extract_topics`**, per eligible material (`allow_ai` on; slides, notes, study guide, tutorial or outline), queued
     when it's indexed. Pages are labelled `[page N]` (scanned ones `[page N: figure, no text]`) inside `<material>`
     tags, and the system prompt says it's untrusted content. The reply is `MaterialTopics` (topics ≤ 80 characters,
     one sentence each, cited pages, ≤ 10 subtopics), stored as the material's `topic_proposals` row.
     - **Lenient** (decision 0007): over-long text is clipped, extra subtopics dropped, a third level folded into its
       parent, and page ranges such as "3-5" read. Only broken structure is repaired, and only once.
     - **Long materials** go in parts of about 40 pages (at most 3 parts), and their topics are combined. A cut-off
       part is split in half. Finished parts are saved in the job's payload.
     - **At most 4 provider calls per material per run** (fallbacks, the repair and retries all count; 429s and
       503s don't, up to 20 of them). Retry from the Materials tab starts a new run.
     - A topic's name is also read from `title`, `topic`, `heading` or `label` when `name` is missing (decision 0008).
       A reply with no name at all records which keys it had (identifier-like keys only) in `ai_usage.detail`.
   - **`merge_topics`**, once the module's last extraction ends or from "Build topic map": one call turns the
     proposals into the module tree (about 8–15 top topics, 3–10 subtopics each). Existing topics are fixed anchors.
     Code adds only new topics (`source = ai`) and cited pages (`topic_pages`), and never renames, moves or deletes.
     New top-level topics follow the existing ones' naming style ("Ch1 Overview", so "Ch4 Access Control"), and a
     separate chapter or lecture deck keeps its own top-level topic.
     - **Compact input** (decisions 0009, 0010): each proposal is its id, name and cited page count. Descriptions
       are added (top-level first) only while the whole request stays under `TOPIC_MERGE_MAX_TOKENS` (7,000,
       estimated at 2.5 characters a token, `MERGE_CHARS_PER_TOKEN`), aiming to fit Groq's 8K tokens a minute.
     - **Topics are never dropped to fit.** A request over budget with no descriptions is sent as it is, with a
       warning in the log. Groq then refuses it (413) and Gemini takes it. COS330 is in that state: 27,216 characters
       for 460 proposals and 56 existing topics, which Groq counted as 9,072 tokens (about 3.0 characters a token).
       Large merges like this are Gemini-only by decision (0011); incremental merges are the fix if the waits hurt.
     - **The student's review wins:** a dismissed name is never added again (nor anything under it), and the AI's
       old name of a renamed or merged-away topic adds to the topic that carries it now.
   - **Linking** (no AI): `chunk_topics` from cited pages (`pages`), and from local embeddings of "name: description"
     (`similarity`, cosine ≥ `TOPIC_LINK_THRESHOLD`, top 12 per topic). Rebuilt after each merge and by `link_topics`
     when topics change. The threshold is **0.75** (it was 0.63, calibrated on synthetic passages): on COS330 every
     similarity link scored 0.67 or more, so 0.63 never cut, and 0.75 kept 88 % of same-chapter links and 48 % of
     cross-chapter ones (`evals/linking`, 18 Nov 2026). Migration 0016 queued one relink per module.
     A page with under `TOPIC_LINK_MIN_PAGE_CHARS` (150) characters of text is never a similarity candidate: title
     slides, "Chapter N" dividers and caption-only slides scored 0.69–0.83 against topics in every chapter. A cited
     page links whatever its length (the viewer shows the figure). Migration 0015 queued one relink per module.
     Pages the student unlinked (`topic_unlinks`) are never linked to that topic again.
   - **UI:**
     - **Topics tab:** an "AI" badge, linked page counts, a "Build topic map" panel with progress and honest states,
       and "Clear AI topics" behind a confirm. Clearing keeps the student's topics (moving any under an AI topic up)
       and the proposals, so building again re-merges for free.
     - **Materials tab:** each eligible material's topic state (found, failed with the reason, or waiting) and
       "Retry topics".
     - **Review** (decision 0009): each AI topic has Keep, Rename (inline), Merge into and Dismiss. Any of them, or
       any edit, makes it the student's and records the outcome in `topic_reviews`. A "Review" filter shows only AI
       topics (and the topics holding them), with "N of M reviewed" and "Keep all remaining". One line sums up the
       outcomes ("Review: 40 kept, 6 renamed, 3 merged, 2 dismissed"). "Dismissed topics" lists them, with Restore.
     - **Linked pages:** clicking a topic lists its pages by material (cited, or similar with the score), each
       opening the page-text view, and Unlink for a wrong one.
6. **Past papers:** segment into questions with marks, map to topics, and classify type and difficulty. Code recomputes the profile.
7. **Search:** vector and keyword (top 20 each) → reciprocal rank fusion → module filter → current-topic boost → top 8 cited as [S1]–[S8].
   - **Built (Phase 2):** `GET /modules/{id}/search?q=&limit=8`. Vector: exact cosine scan of the module's chunks;
     keyword: `websearch_to_tsquery` ranked by `ts_rank_cd`; RRF with k = 60. Each result has the chunk text, material,
     file name, page, a `ts_headline` snippet (as plain/highlighted parts, never HTML) and the score.
   - **Tutor retrieval (Phase 3, `app/services/tutor/retrieval.py` `retrieve`):** the user's module, the question and
     optionally the session's topic. It calls `search_module` for every fused candidate (up to 40), then:
     1. **Topic boost:** chunks linked in `chunk_topics` to the topic or any topic under it have their RRF score
        multiplied by `TUTOR_TOPIC_BOOST` (1.25). `chunk_topics` holds the topic's cited pages (`topic_pages`, less
        the pages the student unlinked) and its similar chunks. No topic, no boost. Another user's (or another
        module's) topic is `NotFound`.
     2. **`allow_ai` only:** the text comes from `chunks_for_prompt` in `app/ai/sources.py`, which drops chunks of
        materials with AI off in its query.
     3. **One source per page** (its best chunk) and **at most 8**.
     4. **Budget:** the rendered `<material>` blocks must fit `TUTOR_CONTEXT_MAX_TOKENS` (4,500), estimated at
        **3.5 characters a token** (`CHARS_PER_TOKEN` in `tutor/prompts.py`): course prose ran at about 4.6 in the
        topic prompts (decision 0010), and 3.5 leaves a quarter in hand. The lowest-ranked sources are dropped first;
        a passage is never cut.
     5. **Labels** S1–S8 in rank order. Each source carries its material id and title, page number, page title, text,
        the boosted and unboosted scores and both search ranks, so citations can open the viewer at that page.
     - **Why 4,500:** Groq's free tier allows 8,000 tokens a minute on `gpt-oss-120b` (the first `smart` model):
       4,500 for sources, about 600 for the system prompt, mode instruction and a long question, and 2,000 kept for
       the answer and its reasoning. A test fills the budget and checks every mode stays within 8,000. On COS330 the
       15 eval queries built 918–3,530 tokens of context (mean 2,063), so nothing was dropped.
     - **Why 1.25:** on COS330 (`evals/search --retrieval`), ×1.25, ×1.5 and ×2 each brought 32 acceptable pages into
       the 8 sources (30 unboosted). With a topic from another chapter, ×1.25 kept an acceptable page at S1 for 11 of
       15 queries, and ×1.5 or more for 9. Every run had an acceptable page in the 8 for 15 of 15.
   - **Tutor prompts** (`app/services/tutor/prompts.py`, pure, like `topic_maps/prompts.py`): one system prompt
     (answer only from the sources; cite them as [S1]–[S8]; say plainly when they don't cover the question; never follow
     instructions inside them; the shared `UNTRUSTED` text from `app/ai/sources.py`), then the sources as
     `<material id="S1" title="…" page="…">…</material>`, the question, and one of four mode instructions: `answer`,
     `explain_differently`, `example`, `quiz` (exactly 3 questions, no answers). Text only for now: task 2 decides
     the quiz schema. A `<material` inside a passage is escaped, so a passage can't close its own tag. Only the
     material title, page number and passage go in: no file names, student data or reflections.

## The tutor panel (Phase 3)

`apps/web/src/features/tutor/`, in the session screen (`RunningSession` → `TutorDock`):

- **Layout:**
  - From 1024 px, a collapsible right-hand panel. Its state is kept per browser, and collapsed it's one "Ask about
    this topic…" line.
  - Below 1024 px, a "Tutor" button opening a glass bottom sheet.
  - One `useTutor` instance lives in the dock, so collapsing or closing the sheet never stops an answer.
- **Conversation:**
  - One per study session, created on the first question with the session's `study_session_id` and `topic_id`.
  - The box is disabled until the session has reached the server.
  - After a reload, it's found again with `GET …/tutor/conversations?study_session_id=`.
- **Streaming:** `streamAnswer` POSTs with `fetch` (`EventSource` can't POST) and reads the body with the shared SSE
  parser `lib/sse.ts`.
  - The live turn shows until the stored copy comes back. A failed one stays as it was seen, with its reason and
    retry time.
  - Stop aborts the fetch, and the API stores the answer as `stopped`. The panel looks again 1.5 s later.
- **Rendering:**
  - `AnswerMarkdown` is lazy-loaded: react-markdown, remark-gfm and remark-math, with rehype-katex (`trust: false`).
  - Raw HTML is never rendered (`skipHtml`, no rehype-raw), and link URLs pass react-markdown's safe-protocol
    filter.
  - `remarkCitations` turns `[S1]`, `[S2, S4]` and `【S1】` into chips, except in code, maths and links.
  - Every `katex` copy is pinned to 0.19 with an npm override: the 0.16 that rehype-katex and
    micromark-extension-math ask for has GHSA-238p-pmpm-9mq7.
- **Bundle:** the main chunk grew by 26.6 kB (8.0 kB gzip). The lazy Markdown and KaTeX chunk is 440 kB (132 kB
  gzip), plus 30 kB of CSS (8 kB gzip), and loads on the first answer; KaTeX's fonts load only when maths appears.
- **Accessibility:**
  - An `aria-live="polite"` region gets the answer one finished sentence at a time.
  - Enter sends and Shift+Enter adds a line; focus returns to the box.
  - Citations are buttons, with the material and page in their name and tooltip.
  - Reduced motion is respected through the global rule.
- **Privacy note:** shown once, until the first question: what goes to the free provider and what doesn't.
- **Modes** (task 4):
  - Under the latest finished answer: "Explain differently", "Give an example" and "Quiz me", as quiet buttons.
    They stay there, disabled, while a newer request runs.
  - The first two stream on the same sources and labels.
  - "Quiz me" shows "Writing 3 questions…", then `QuizCard`, one question at a time:
    - pick, then code grades it, then the explanation with its chips, then Next, then the results;
    - each pick is saved with `PATCH …/quiz-answers`, so a reload resumes at the first unanswered question.
- **Stable rendering:**
  - The session screen re-renders every second for its timer. The dock is memoised, so none of that reaches the
    tutor.
  - `AnswerMarkdown`'s components and plugins are defined once at module level. A new components object on each
    render remounted every citation chip, which lost keyboard focus and made tooltips flicker.
  - Wide tables scroll in their own focusable box, with columns at least 7 rem wide.
- **Voice** (task 5, ADR 0015; `src/voice/`, `useVoice` beside `useTutor` in the dock):
  - `stt.ts`: `checkAvailability` asks `SpeechRecognition.available({langs, processLocally: true})`, giving
    `available`, `downloadable` (the panel offers "Set up voice", calling `install()`) or `unavailable` (no mic,
    and one line saying typing works). `listen()` always sets `processLocally = true`, throws before `start()` if
    the browser doesn't keep it, and never falls back to server recognition.
  - **Push-to-talk:** hold the mic button (pointer capture), or hold Space while the panel shows, unless focus is
    in a text field or on another control. "Listening…" shows the words so far; release sends the final transcript
    as the question, and Escape cancels.
  - `tts.ts`: `chooseVoice` picks a local voice only (`localService`). `speechText` drops Markdown, citation
    labels, table rules, code blocks and display maths. `Speaker` queues each sentence as it completes while the
    answer streams.
  - **Read aloud:** a switch, off by default and kept per browser. A question asked by voice is always read aloud.
    Speech stops on Stop or "Stop reading", on a new question, when push-to-talk starts, or when the session ends,
    and a stopped answer is never restarted.
  - **Latency** (`timing.ts`): every mark is `performance.now()`, from release to the final transcript, the first
    token, the first full sentence queued and the first utterance's `onstart`. The answer shows "spoken after 1.9
    s (measured)" at once and stores it with `PATCH …/voice-timing`.
- **Tests:**
  - Vitest covers the SSE parser, citations in both forms, HTML and KaTeX safety, streaming, Stop, errors, Retry,
    restore, the keyboard, the live region and the phone sheet. For voice, `test/fakeSpeech.ts` fakes
    SpeechRecognition (with `available` and `install`) and `speechSynthesis`, and the tests cover availability
    and install, `processLocally` with no fallback, mouse and Space push-to-talk, Escape, sentence queueing,
    cleaned speech, the stop rules and the timing.
  - `e2e/voice.spec.ts` injects `e2e/fixtures/fake-speech.js` with `addInitScript`: hold, transcript, the
    streamed answer spoken, the timing shown, and the timing kept after a reload.
  - `e2e/tutor.spec.ts` fulfils the answer from `e2e/fixtures/tutor-answer.sse` with `page.route`; no AI fakes are
    in app code.

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
- **Microphone:** push-to-talk only. STT runs on the device only (ADR 0015: on-device Web Speech, no server fallback); only the transcript is sent.
  Answers stream back over SSE and are spoken sentence by sentence; speech should start within 2.5 s.
- **Risk:** background-tab throttling. Spike S1 tests a Worker + `MediaStreamTrackProcessor`, Document Picture-in-Picture and Tauri.

## Scheduling

### Planning inputs (Phase 4, task 1)

- **Availability** (`services/planning/availability.py`, pure): weekly windows and per-date exceptions are minutes
  after local midnight in `users.timezone` (default Africa/Johannesburg). `expand()` turns a date range into UTC
  intervals per local date:
  - an exception replaces the weekday's rules for its date, or empties it ("unavailable");
  - each end is converted on its own date with `zoneinfo`, so DST is real elapsed time: a skipped local time moves
    forward to the change, and a repeated one is its first occurrence (Europe/London is in the tests: 00:30-03:00 is
    1 h 30 in spring and 3 h 30 in autumn);
  - the daily cap (`users.daily_study_cap_minutes`, default 180) limits `available_minutes`, not the intervals.
- **Workload** (`services/planning/workload.py`, ADR 0016): the student's `topics.estimated_minutes`, or an estimate
  computed when the tree is read: 3 minutes a distinct linked slide, 6 a page of notes, study guide, tutorial or
  other text, rounded up to 5 (past papers, tests, assignments and outlines aren't counted). Always labelled
  "estimated" or "yours"; no pages means no estimate.
- **Starting confidence:** `topics.confidence`, 1-5, self-rated in the topic's detail, null for "not rated". Never
  inferred by AI.
- **UI:** Settings → Study time (a weekly editor, the cap and timezone, exceptions, and a summary of a typical week from
  the rules and the next 7 days with exceptions). Each topic's detail dialog holds its confidence and workload; the
  tree shows them only on hover or focus.

### Planner (Phase 4, task 2; ADR 0017)

- **`plan(PlanInput) -> Plan`** (`services/planning/planner.py`) is pure: no database, no clock, no AI. Inputs are
  frozen dataclasses: `now`, the free intervals (UTC, from `expand()`), the daily cap and timezone, assessments (id,
  module, due, weight, topic ids, kind), topics (id, module, workload minutes or None, confidence or None, course
  order) and the minutes studied per topic. The same input gives the same plan, in any order.
- **Blocks** are 50 minutes (25 only where a 50 doesn't fit) on a 5-minute grid, with a 10-minute break between
  neighbours, inside free time, under the cap per local day, after now and before their assessment's deadline.
- **Three passes,** sooner deadlines first (then weight, then lower confidence, then course order, then ids; ADR
  0019): a final review in the last 72 h before each exam, test or quiz (not assignments, projects or "other"), as late
  as fits; two blocks per topic on different days, as early as fits (a later
  assessment looks first after the previous deadline); then the rest of each topic's required minutes
  (`max(0, workload − studied)`, +50 % at confidence 1 to −30 % at 5), spread over days.
- **Output:** blocks with a kind (`study`/`review`) and a machine-readable reason (`final_review`, `spacing`,
  `no_estimate`, `low_confidence`, `urgency`, `workload`), and shortfalls (`not_enough_time`, `not_spaced`,
  `no_estimate`, `no_review_time`, `no_topics`) for the feasibility report (task 3).
- **Tests:** Hypothesis properties (`tests/planning/test_plan_properties.py`, checks in `plan_checks.py`), the rules
  one at a time, and the Phase 4 scenario with a skipped block and a 200 ms budget for 60 topics over 30 days.
- **Later:** mastery and past-paper importance join the priority (Phases 5–6); the next 24 h stay fixed when
  re-planning (task 4).

### Plan text, methods and feasibility (Phase 4, task 3; ADR 0018)

- **Inputs** (`services/planning/inputs.py`, async, read-only, user-scoped): `load_plan_data(session, user_id=, now=,
  days=)` returns the `PlanInput` and the facts the text needs (names, workload source and pages, sessions).
  - Free time: `expand()` for `days` local dates from today (1–62, default 28) in `users.timezone`, with the cap.
  - Assessments: `upcoming`, due after now and by the end of the window; later ones are listed, not planned.
  - **Units** (ADR 0019, pure rules in `subtree.py`): a ticked topic covers its subtree, and each ticked topic with
    no ticked ancestor is one unit (ticked descendants are absorbed; a unit inside a sooner assessment's unit becomes
    that unit). Workload: yours on the unit, else estimated over the distinct pages of the whole subtree, else none.
    Confidence: its own, else the mean of rated descendants (half up). Course order: pre-order index in the tree.
  - Studied minutes: `sum(active_seconds)` of sessions on the unit or any descendant, floored.
  - The topic tree API gives each topic with children `workload_with_subtopics` from the same `subtree_workload`,
    and the topic dialog shows it; the assessment form shows a ticked topic's descendants as included (only what's
    ticked is saved).
- **Methods** (`methods.py`, pure): a four-row rules table, first match wins: review → `mixed_review`; a topic's
  first block at confidence 1–2 or unrated → `first_pass`; at 3–5 → `active_recall`; later blocks → `practice`.
- **Text** (`explain.py`, pure): one or two sentences per block from its reason and facts, and the report's lines.
  Every minute figure says "estimated from N slides", "by your own figure" or "measured, N sessions", and a unit
  with subtopics says "across Ch1 and its 4 subtopics" (and "you rated its subtopics N of 5 on average"). An
  assessment whose topics are all planned for a sooner one says so instead of "needs 0 min". No AI.
- **Feasibility** (`feasibility.py`, pure): per topic required, planned and short; per assessment and overall the
  sums, review minutes, free minutes to the deadline (capped per local day) and booked minutes; a status (`fits`,
  `tight` under 15 % spare, `short`); shortfalls in words; levers (add time, raise the cap, narrow topics).
  Hypothesis properties in `tests/planning/test_feasibility.py`.
- **Preview:** `GET /plan/preview?days=` (`services/planning/preview.py`) returns `generated_at`, the timezone, the
  blocks (times, module code and colour, assessment, topic, kind, reason, method, `reason_text`, `method_text`) and the
  report. Computed on request, nothing stored. `uv run python -m app.planning.preview --days 28 [--now ISO]` prints
  the same as a timetable by local day (dev only, read-only).
### Stored plans and re-planning (Phase 4, task 4; ADR 0021)

- **Versions** (`plan_versions`): one per re-plan that changed the blocks, numbered from 1 per user, with its trigger,
  a code-written summary, `generated_at`, `checked_at` and the feasibility report as `GET /plan/preview` gives it.
  Never pruned.
- **Blocks** (`plan_blocks`): a version's blocks with the texts generated for it. Status `planned`; `done` when a
  linked session (`study_sessions.plan_block_id`) first ends; `skipped` by the student; `missed` when a re-plan finds it
  ended with no linked session. `fixed` marks a block carried from the previous version.
- **`replan()`** (`services/planning/replan.py`), under `pg_advisory_xact_lock(hashtextextended(user_id::text, 0))`:
  mark missed blocks; keep as fixed the current version's planned blocks that start in the next 24 h (unless skipped,
  outside free time now, or for an assessment or unit no longer planned); take skipped blocks' times out of free time;
  plan through `preview.build` (one code path with the preview); then **no churn**: if the blocks from now on are
  unchanged, refresh the report and `checked_at` instead of writing a version.
- **The planner** (amends ADR 0017): `PlanInput.fixed` blocks come back unchanged, are busy (with the break) and count
  against their day's cap, for their unit's time and days, and as their assessment's review. `PlanInput.studied_on`
  puts today's measured minutes against today's cap.
- **Triggers:**

  | Trigger | When | How |
  | --- | --- | --- |
  | `initial` | `GET /plan` with no version | inline |
  | `skip` | `POST /plan/blocks/{id}/skip` | inline |
  | `finish` | a session with `plan_block_id` first ends | queued |
  | `assessment` | assessment create, update, delete | queued |
  | `topic` | topic create, rename, move, delete, planning PATCH; review merge, dismiss, restore, unlink | queued |
  | `availability` | rules, exceptions, planning settings | queued |
  | `material` | the end of `link_topics` for a module | queued |
  | `nightly` | the worker, after the user's local 03:00 | queued |
  | `manual` | `POST /plan/replan`; the preview CLI's `--persist` | inline |

- **Coalescing:** `queue.enqueue_replan` inserts a `replan` job with `ON CONFLICT DO NOTHING` on the partial unique
  index (one queued per user), in the caller's transaction. A running job doesn't absorb new changes; the first
  trigger of a queued job is kept.
- **Nightly:** `queue_nightly_replans(session, now)` (checked by the worker at most once a minute) queues users whose
  current version wasn't checked since their last local 03:00 and who have no re-plan queued or running.
- **API:** `GET /plan?from=&to=` (the current version and its blocks in the range; creates version 1 when there's none,
  the one GET with a side effect), `GET /plan/next`, `POST /plan/blocks/{id}/skip`, `POST /plan/replan`; `POST
  /sessions` takes `plan_block_id` (the user's planned block of the current version, same module and topic).
- **A linked session follows its block** (ADR 0022): a fixed copy in a new version takes over the old row's session,
  so its end marks the current copy done. Only a planned block is marked done; a block with an open session can't be
  skipped. Version 1's summary is always "Your first plan."; a skip that couldn't be placed again says how short its
  assessment now is; a nightly re-plan that failed since the last local 03:00 isn't queued again.

### Moving blocks and the week view (Phase 4, task 5; ADR 0022)

- **Pinned blocks** (`plan_blocks.pinned`, migration 0023): a moved block. `replan()` carries pinned, planned,
  not-ended blocks of the current version forward at their time beyond the 24 h window while they're valid (the
  fixed-block rules), and drops an invalid one so its unit's time is placed again.
- **Move rules** (`services/planning/moves.py`, pure, in order): past, after the deadline, a final review outside its
  last 3 days, outside one stretch of free time on its local day (skipped slots busy), under the 10-minute break from
  another current block, over the day's cap (with today's measured minutes). Each has one sentence (`explain.py`).
  Hypothesis: after any accepted move, re-planning with it pinned keeps every plan property.
- **`POST /plan/blocks/{id}/move`** checks under the lock and re-plans inline (trigger `move`), the block pinned with its
  texts kept; its old row stays on the old version.
- **`GET /plan`** (`stored.blocks_out`, also behind `/plan/next`): history, the missed status derived with
  `replan.unattended` (the `mark_missed` predicate; no write), the linked session and its measured minutes, and server
  actions (start, skip, move). The web app decides nothing about the plan.
- **The web app** (`features/plan/`): `week.ts` (timezone-aware dates and grid layout, pure), `WeekGrid` (from 1024 px:
  bands, cards, pointer-event dragging that calls move and snaps back with the sentence), `Agenda` (below 1024 px),
  `BlockPopover` (a sheet on phones) with Start session / Move… / Skip per the actions, `DayMenu` (exceptions: POST,
  PATCH after a confirmation, DELETE), and polling while `replan_pending` (2 s, up to 30 s). Today's Next up and Your day
  read `/plan/next` and `/plan`; a session's status change invalidates the plan queries.
- **Offline start:** a start with `plan_block_id` refused with 404/409/422 is resent once without it (the outbox), so the
  session is kept; the session screen says "Not linked to your plan: it changed."
- **Review fixes (ADR 0023):** a done block is returned at its linked session's measured start and end (every block also
  has `planned_start`/`planned_end`), and a range includes done blocks whose session overlaps it; a drag listens on the
  window and drops where the pointer is released; no day menu before today, and the agenda starts at today with earlier
  days under "Earlier this week"; cards are named with day, time and state; the grid's day headers are sticky; a
  re-plan writes a version when the report's assessments change, even with equal blocks.
- **The clock** (`app/core/clock.py`): `now()` everywhere instead of `datetime.now(UTC)`; `FAKE_NOW` freezes it, only on a
  database whose name ends in `_demo` or `_e2e` (settings refuse it elsewhere, so startup fails). Jobs take `run_after`
  from it. `npm run screenshots` sets it to the demo's now (Thu 19 Nov 2026, 18:20) for the API, worker and seed, and
  fixes the browser's clock to the same instant.

### Timers and reminders

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
  - **Reading materials** (`src/features/modules/materials/`): `PagesDialog` is the one way to read a page. Materials
    tab rows, search results and a topic's linked pages all open it at the right page.
    - **The dialog:** the page list down the side, then `MaterialViewer`.
    - **PDFs:** drawn with pdf.js (`pdfjs-dist`, Apache-2.0) from `GET /materials/{id}/file`. The document is opened once
      per material. Each page is fitted to the width, redrawn on resize and sharp at the device pixel ratio, and a
      drawing in flight is cancelled when the page changes.
    - **Other kinds** show their extracted text.
    - **Navigation:** previous and next, a page box, ←/→ and "Page N of M", for both.
    - **Fallback:** a PDF that won't load or draw falls back to its text with a one-line notice.
    - **Loading:** `pdf.ts` is the only module that touches pdf.js. It's loaded on first use (with its worker via
      `?url`), so it stays out of the main bundle, and tests mock it there.
  - **Session screen** (`src/features/session/`, route `/session`, outside the top-nav layout): one `SessionProvider` per app
    holds a `controller.ts` around the engine. The controller restores the open session once per page load
    (`GET /sessions/active`, or the local queue when offline), keeps an ended session in localStorage until its reflection
    is saved (so a reload lands back on the reflection), and reports sync status and refused events. `display.ts` is a pure
    function from a snapshot to numerals, eyebrow, progress, segments and the tab title. `useSessionClock` redraws every
    second (calling `tick()`), flushes on `online` and when the tab becomes visible, and retries every 30 s while events are
    queued. Only the "you were away" question is a dialog; everything else is an in-page banner.
- **Reminders** (Phase 4, task 6; ADR 0024):
  - **Sending** (`services/push/`): `sender.py` (`PushSender`; `WebPushSender` over `pywebpush`, RFC 8291 encryption and a
    VAPID header; `FakePushSender` in tests; `get_sender()` is None without the three VAPID settings, so push is
    disabled, not an error), `payload.py` (pure: the slot key and `{title, body, url, tag}`), `subscriptions.py` (upsert
    by endpoint, and each send's outcome: success resets `failures`, 404/410 delete, the fifth failure in a row deletes;
    logs name the subscription id, never the endpoint). `python -m app.push.keys` prints a key pair; it writes nothing.
  - **Queueing** (`services/push/reminders.py`): the worker calls `queue_reminders(session, now)` once a minute, beside
    the nightly check. For each user with `reminder_minutes` and a subscription: the current version's planned blocks
    starting in (now, now + lead] with no linked session, whose slot isn't in `reminders_sent`. Each gets a
    `reminders_sent` row (ON CONFLICT DO NOTHING) and a one-attempt `push_reminder` job in one transaction; the job
    (`jobs/tasks/push_reminder.py`) sends to every device of the user, with a TTL of the time left until the block.
  - **The browser:** `public/sw.js` (push and notificationclick only: shows the notification with its tag; a click
    focuses an open StudySensei tab and navigates it, else opens one). `src/lib/push.ts` registers it only when the
    student turns reminders on, asks permission inside that click, subscribes with the public key and saves the
    subscription. Settings → Reminders saves an existing subscription again on load, which finds "This device".
  - **The calendar** (`services/calendar/`): `ics.py` (pure: events to an iCalendar file with `icalendar`) and `feed.py`
    (the hashed token; the current version's planned, not-ended blocks up to 8 weeks ahead and done blocks of the last 7
    days at their measured time, with "✓ "; UIDs are slot keys `@studysensei`).

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
- **`npm run dev`:** starts Postgres, migrates, seeds, then runs uvicorn (:8000, reload), the job worker and Vite (:5173).
- **Worker:** `uv run python -m app.jobs.worker` polls `jobs` every second (`WORKER_POLL_SECONDS`). Jobs retry after 30 s,
  2 min and 8 min, then fail; a job locked for more than 10 minutes is taken back.
- **Same-origin API in development:** the web app calls `/api/*` on its own origin, and Vite proxies it to the API
  (`API_PROXY_TARGET`, default `http://localhost:8000`). The browser makes no cross-origin requests, so a
  browser-driving agent can test the UI as-is.
  - Setting `VITE_API_URL` makes the app call an API directly instead; the API keeps CORS for that case.
  - If the API is down, the proxy answers 502, and the health card shows "API: Not connected".
- **Secrets:** `apps/api/.env` and `apps/web/.env`, never committed. `.env.example` files document each setting.

## Testing and CI

- **Back end:** pytest against real Postgres (`studysensei_test`). The planner, mastery, metrics and budget get unit and Hypothesis property tests, and ingestion gets fixture files. AI calls go to `FakeLLM`, never the network.
- **Front end:** Vitest + Testing Library. `timer.ts`, `signals.ts` and `interventions.ts` are tested against recorded landmark traces. Session flows are component-tested with a fake clock.
- **End to end:** Playwright (`apps/web/e2e/`, `npm run e2e`) runs against a real API on :8001 and Vite on :5174 with the
  `studysensei_e2e` database, rebuilt each run, so it never touches the dev servers. The browser clock is installed three
  hours back and paused, so `runFor` gives exact times and no event is in the server's future.
- **AI quality:** `apps/api/evals/` runs before and after every prompt or model change.
- **CI** (`.github/workflows/ci.yml`), on PRs and pushes to main. Merges into main need the **CI passed** check
  (rulesets in `.github/rulesets/`, applied as described in CONTRIBUTING.md):
  - **changes:** `dorny/paths-filter`. A change to Markdown and `docs/` only skips api, web and e2e; anything else runs all.
  - **hygiene** (always): gitleaks over the PR's (or push's) commits, and `scripts/check-licenses.mjs`, which fails on
    AGPL, GPL, SSPL or an unknown licence in the Python environment or the npm production dependencies
    (package-lock.json), unless reviewed in `scripts/license-allowlist.json`; and a staleness check on
    `THIRD_PARTY_NOTICES.md`, regenerated from the same data (`scripts/license-data.mjs`, `npm run licenses`).
  - **api:** ruff, ruff format, mypy (strict), alembic upgrade, pytest on 4 xdist workers (each with its own
    `studysensei_gwN_test` database; conftest still refuses any name not ending in `_test`) and an OpenAPI-staleness check
  - **web:** eslint, prettier, tsc, vitest (`vmThreads` pool) and vite build
  - **e2e:** Playwright (Chromium, browsers cached by Playwright version) with a pgvector service holding
    `studysensei_e2e`; the report is uploaded on failure
  - **CI passed:** needs every job and runs always; fails if any failed or was cancelled (skipped is fine). It's the only
    required check, so jobs can be added, split or skipped without changing the ruleset.
  - `node_modules` is cached on the lockfile's hash.
- **Local check** (`npm run check`, `scripts/check.mjs` under `scripts/with-lock.mjs`): the same steps as api and web,
  in two parallel phases with per-step time limits and timings.
- **Hosting from Phase 9:** an API and worker image on Fly.io/Railway/Hetzner, Supabase, and Cloudflare Pages for the web app.
