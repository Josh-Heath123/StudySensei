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
| Background jobs | Worker polling a `jobs` table with `FOR UPDATE SKIP LOCKED` (decision 0004) | No Redis; jobs survive restarts |
| Embeddings | Local `fastembed`, `BAAI/bge-small-en-v1.5` (384 dims, CPU) | Free, private, fast enough |
| LLM access | Our own `LLMClient` with **one OpenAI-compatible adapter** | ~200 lines we control ([0002](decisions/0002-free-ai-providers.md)) |
| Models | `smart`: Groq `openai/gpt-oss-120b` → `gemini-3.5-flash-lite` → `gemini-3.8-flash`; `bulk`: `gemini-3.5-flash-lite` → Groq `openai/gpt-oss-20b`; `vision` (any image): `gemini-3.5-flash-lite` → Groq `qwen/qwen3.8-27b` → `gemini-3.8-flash`; optional Ollama last in the text roles | Zero cost, ordered by free-tier daily limits and latency; roles live in config (see AI integration) |
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
  app/services/      search/ (chunking, embedding, indexing, search), planning/, mastery/, profile/, pastpapers/
  app/ai/            client.py (LLMClient), adapter.py (OpenAI-compatible), routes.py, budget.py, usage.py, sources.py, ping.py; later prompts/, retrieval.py
  app/jobs/          queue.py (enqueue, claim, retry), worker.py, kinds.py, tasks/ (extract_text, index_material, …)
  app/storage/       Storage interface + LocalStorage (data/materials), keys {user_id}/{sha256}
  alembic/           migrations
  tests/             pytest against real Postgres (studysensei_test)
  evals/             fixed AI test sets + results/
  scripts/           export_openapi.py
apps/web/            React app
  src/app/           routes, layout, top navigation, providers
  src/features/      today/, modules/, session/, plan/, practice/, insights/, settings/
  src/vision/        camera.ts, vision.worker.ts, signals.ts, calibration.ts, rollup.ts   (Phase 7)
  src/voice/         stt.ts, tts.ts                                                       (Phase 3)
  src/session-engine/ timer.ts, interventions.ts                                         (Phase 1/7)
  src/lib/api/       openapi.json, generated schema.d.ts, typed client (openapi-fetch)
  src/ui/            design-system components (shadcn/ui restyled to docs/DESIGN.md; tokens in src/index.css)
apps/web/e2e/        Playwright specs
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
| Topics | `GET /modules/{id}/topics` (nested tree; each node has `linked_pages`), `POST /modules/{id}/topics`, `PATCH/DELETE /topics/{id}`, `POST /topics/{id}/move` `{parent_id, position}` (any edit makes an AI topic `source = user`) |
| Topic maps | `GET /modules/{id}/topic-map` (eligible / analysed / pending / failed materials, `merging`, `waiting_until`, `last_error`, `merged_at`), `POST /modules/{id}/topic-map/build` (decision 0006); `GET /modules/{id}/topic-map/materials` (each eligible material: `analysed` / `failed` with `error` / `waiting`), `POST /materials/{id}/topics/retry` (a new run; 422 if its topics aren't found), `DELETE /modules/{id}/ai-topics` (`{deleted}`; decision 0007) |
| Assessments | `GET/POST /modules/{id}/assessments`, `GET /assessments?status=` (all modules), `GET/PATCH/DELETE /assessments/{id}` (responses include `topic_ids`; sending `topic_ids` replaces the whole set) |
| Tasks | `GET/POST /modules/{id}/tasks`, `GET /tasks?status=` (all modules), `GET/PATCH/DELETE /tasks/{id}` (`status: "done"` sets `completed_at`) |
| Sessions | `POST /sessions`, `GET /sessions/active`, `GET/DELETE /sessions/{id}`, `POST /sessions/{id}/events`, `PUT /sessions/{id}/reflection`, `GET /modules/{id}/sessions?limit=&offset=` (a page `{items, total, limit, offset}`: the open session first, then newest first; limit 1–100, default 20), `GET /modules/{id}/sessions/summary?week_start=` (session count and active seconds, all time and since `week_start`) |
| AI | `GET /ai/status`: per provider whether it's configured (`key_set` is yes/no only), each role's models in order, and per model `used_today` / `daily_budget` / `resets_at` for the current user |
| Materials | `POST /modules/{id}/materials` (multipart: `file`, `kind`, `title?`, `allow_ai`; 413 over 50 MB, 415 wrong type, 409 same file in the module), `GET /modules/{id}/materials`, `GET/PATCH/DELETE /materials/{id}` (PATCH: title, kind, allow_ai), `POST /materials/{id}/retry` (failed only), `GET /materials/{id}/pages` (page number, title, char count, is_scanned), `GET /materials/{id}/pages/{n}` (adds the text) |

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
| 503 | `AIUnavailable`: no provider configured, or every model rate-limited or out of budget; `Retry-After` when known | a string |

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
| Materials | `materials`, `material_pages` (text per page, `is_scanned`), `chunks` (one page each: page number, position, text, token count, `embedding vector(384)`, generated `tsv tsvector`), `chunk_topics` (chunk, topic, score, method `pages`/`similarity`) |
| Topic maps | `topic_proposals` (one per material: validated AI JSON + provider and model), `topic_pages` (pages each topic was drawn from) | Decision 0006 | `materials.kind`: slides, notes, study_guide, tutorial, past_paper, test, assignment, outline, other; `status`, `error`, `page_count`, `allow_ai`; `UNIQUE (module_id, sha256)` |
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
- 0004 is data only: existing module colours mapped to the design-system swatches (nearest hue)
- `chunks` (0007), with a GIN index on `tsv` and no vector index (decision 0005)
- `ai_usage` (0008): user, provider, model, role, purpose, input/output tokens, latency, outcome (`ok`, `rate_limited`,
  `error`, `invalid_json`, and `timeout` from 0009). Never prompt or reply text. Roles `vision` (0010) and `long` (0011).
  0012 adds `job_id` (the job that made the call), `detail` (why it failed: HTTP status and provider message, or
  what didn't validate; ≤ 300 characters) and the `truncated` outcome.
- `topic_proposals`, `topic_pages`, `chunk_topics` (0011), plus `UNIQUE (id, module_id)` on `chunks`; the migration
  queues `extract_topics` for every eligible indexed material.

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

Decision 0002. Everything goes through `app/ai/`; nothing else talks to a provider.

- **One adapter:** `adapter.py` speaks the OpenAI chat-completions API over httpx (`POST {base}/chat/completions`,
  `GET {base}/models`) for every provider:
  - Gemini (primary): `https://generativelanguage.googleapis.com/v1beta/openai/`, `GEMINI_API_KEY`
  - Groq (fallback): `https://api.groq.com/openai/v1`, `GROQ_API_KEY`
  - Ollama (optional): `http://localhost:11434/v1`, no key, on only when `OLLAMA_MODEL` is set (then last in every role, no budget)
- **Roles, in config** (`AI_SMART`, `AI_BULK`, `AI_VISION` in `app/core/config.py`): ordered lists of routes, each
  a `"provider/model"` plus a `reasoning_effort`:

  | Role | Used for | Models, in order | Thinking |
  | --- | --- | --- | --- |
  | `smart` | tutor, topic maps | `groq/openai/gpt-oss-120b`, `gemini/gemini-3.5-flash-lite`, `gemini/gemini-3.8-flash` | `low` |
  | `bulk` | classification, tagging | `gemini/gemini-3.5-flash-lite` (`minimal`), `groq/openai/gpt-oss-20b` (`low`) | as listed |
  | `vision` | any request with an image: scanned pages, figure slides | `gemini/gemini-3.5-flash-lite`, `groq/qwen/qwen3.8-27b`, `gemini/gemini-3.8-flash` | `low` |
  | `long` | whole documents in one prompt: topic extraction and the module merge | `gemini/gemini-3.5-flash-lite`, `gemini/gemini-3.8-flash`, `groq/openai/gpt-oss-120b` | `low` |

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

  | Model | Levels | Default |
  | --- | --- | --- |
  | `gemini-3.8-flash` | `low`, `medium`, `high` (no `minimal`: asking for it is a 400) | `medium` |
  | `gemini-3.5-flash-lite` | `minimal`, `low`, `medium`, `high` | `minimal` |
  | Groq `openai/gpt-oss-120b`, `openai/gpt-oss-20b` | `low`, `medium`, `high` | not documented |
  | Groq `qwen/qwen3.8-27b` | `low`, `medium`, `high` (also its own `none` / `default`) | not documented |

  A call can ask for more with `complete_text(…, reasoning_effort="high")`. The ping always uses `minimal`.

- **Free-tier limits and budgets** (`AI_DAILY_BUDGET`, requests per day, about 10 % under the limit). Google no longer
  publishes free-tier numbers. These are the per-project quotas that AI Studio and 429 replies reported in Sept–Nov 2026.
  Check yours at aistudio.google.com/rate-limit and console.groq.com/settings/limits.

  | Model | Free tier | Budget | Resets | Images |
  | --- | --- | --- | --- | --- |
  | `gemini-3.8-flash` | 5 RPM, 20 RPD | 18 | midnight Pacific | yes |
  | `gemini-3.5-flash-lite` | 15 RPM, 500 RPD | 450 | midnight Pacific | yes |
  | Groq `openai/gpt-oss-120b` | 30 RPM, 1K RPD, 8K TPM, 200K TPD | 900 | midnight UTC (assumed) | no |
  | Groq `openai/gpt-oss-20b` | 30 RPM, 1K RPD, 8K TPM, 200K TPD | 900 | midnight UTC (assumed) | no |
  | Groq `qwen/qwen3.8-27b` | 30 RPM, 1K RPD, 8K TPM (3 images per request) | 900 | midnight UTC (assumed) | yes |

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
  - **What moves on to the next model** (decision 0007): only "this model can't take it now". That means a 429, a
    timeout, a lost connection, or a 413 (too large for that model's limits).
    - A 429 or 5xx is first retried once on the same model when the wait (the `Retry-After` header or HTTP date,
      Gemini's `retryDelay`, or 2 s × 2ⁿ backoff, plus jitter) is at most `AI_MAX_WAIT_SECONDS` (20 s). Otherwise
      the model cools down (at least a minute).
    - A persistent 5xx raises `AIUnavailable` (the job waits).
    - Any other refusal (400, 401, 404…) raises `AIRequestFailed` with the provider's message, and the job fails at
      once.
    - Invalid output is repaired once at most and never moves to another model.
  - **Cut off:** a reply with `finish_reason` `length` raises `AITruncated` (logged `truncated`, not repaired).
  - **Call budgets:** a caller can pass a `CallBudget` (calls and repairs for one unit of work, every fallback
    included). Topic jobs count their calls across retries from `ai_usage.job_id`.
  - **Error text:** a failed request reads like `gemini: HTTP 400: Thinking level MINIMAL is not supported…`. Only the
    body's `error.message` is used, trimmed to 300 characters, never the request or headers.
  - **Budgets** (`budget.py`): the user's `ai_usage` rows for that model since the provider's last local midnight
    (`AI_QUOTA_TIMEZONE`). They count `ok`, `error`, `invalid_json`, `timeout` and `truncated`. A 429 isn't counted:
    it was refused before running (decision 0007).
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
  - For COS330, the student turns `allow_ai` off on their own `u23541475_*` submissions.
- **Checking keys:** `uv run python -m app.ai.ping` sends "Reply with the single word: pong" to every configured model
  at `minimal` effort. It prints `→ provider/model …` before each call, then `ok` with the latency and reply, or `FAIL`
  with the reason, and says if a model ID is missing from the provider's `/models` list. Each model gets 30 s in total,
  so a slow one can't hold up the rest.
- **Tests never call a provider:** `tests/conftest.py` blanks the key variables (the environment beats `.env`) and
  installs a client whose transport fails any request. AI tests script replies with `FakeLLM` (`tests/fakes.py`).
- **AI suggests, code decides:** AI never changes the plan, deletes data or sends notifications.
- **Untrusted input:** uploaded documents are untrusted, and retrieved text is labelled as source material in prompts.
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
     - **At most 4 provider calls per material per run** (fallbacks, the repair and retries all count). Retry from
       the Materials tab starts a new run.
   - **`merge_topics`**, once the module's last extraction ends or from "Build topic map": one call turns the
     proposals into the module tree (about 8–15 top topics, 3–10 subtopics each). Existing topics are fixed anchors.
     Code adds only new topics (`source = ai`) and cited pages (`topic_pages`), and never renames, moves or deletes.
     New top-level topics follow the existing ones' naming style ("Ch1 Overview", so "Ch4 Access Control"), and a
     separate chapter or lecture deck keeps its own top-level topic.
   - **Linking** (no AI): `chunk_topics` from cited pages (`pages`), and from local embeddings of "name: description"
     (`similarity`, cosine ≥ 0.63, top 12 per topic). Rebuilt after each merge and by `link_topics` when topics change.
   - **UI:**
     - **Topics tab:** an "AI" badge, linked page counts, a "Build topic map" panel with progress and honest states,
       and "Clear AI topics" behind a confirm. Clearing keeps the student's topics (moving any under an AI topic up)
       and the proposals, so building again re-merges for free.
     - **Materials tab:** each eligible material's topic state (found, failed with the reason, or waiting) and
       "Retry topics".
     - The review UI comes next.
6. **Past papers:** segment into questions with marks, map to topics, and classify type and difficulty. Code recomputes the profile.
7. **Search:** vector and keyword (top 20 each) → reciprocal rank fusion → module filter → current-topic boost → top 8 cited as [S1]–[S8].
   - **Built (Phase 2):** `GET /modules/{id}/search?q=&limit=8`. Vector: exact cosine scan of the module's chunks;
     keyword: `websearch_to_tsquery` ranked by `ts_rank_cd`; RRF with k = 60. Each result has the chunk text, material,
     file name, page, a `ts_headline` snippet (as plain/highlighted parts, never HTML) and the score. The topic boost
     comes with the tutor (Phase 3).

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
  - **Session screen** (`src/features/session/`, route `/session`, outside the top-nav layout): one `SessionProvider` per app
    holds a `controller.ts` around the engine. The controller restores the open session once per page load
    (`GET /sessions/active`, or the local queue when offline), keeps an ended session in localStorage until its reflection
    is saved (so a reload lands back on the reflection), and reports sync status and refused events. `display.ts` is a pure
    function from a snapshot to numerals, eyebrow, progress, segments and the tab title. `useSessionClock` redraws every
    second (calling `tick()`), flushes on `online` and when the tab becomes visible, and retries every 30 s while events are
    queued. Only the "you were away" question is a dialog; everything else is an in-page banner.
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
- **CI** (`.github/workflows/ci.yml`), on PRs and pushes to main or rebuild:
  - **api:** ruff, ruff format, mypy (strict), alembic upgrade, pytest (pgvector service) and an OpenAPI-staleness check
  - **web:** eslint, prettier, tsc, vitest and vite build
  - **e2e:** Playwright (Chromium) with a pgvector service holding `studysensei_e2e`; the report is uploaded on failure
- **Hosting from Phase 9:** an API and worker image on Fly.io/Railway/Hetzner, Supabase, and Cloudflare Pages for the web app.
