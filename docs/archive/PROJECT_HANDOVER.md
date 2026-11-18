# StudySensei: project handover

> Archived. Personal identifiers redacted on 18 Nov 2026.

Snapshot of 17 Nov 2026, 21:45. For current status see ROADMAP and PROGRESS.

- **Written:** 17 Nov 2026, about 21:45 SAST, by Claude (the StudySensei Project chat in claude.ai) for a fresh session.
- **How it was written:** the repository at `C:\StudySensei` was read directly through the device bridge: files, docs,
  ADRs, migrations, config and git state. Conversation history from the build was used only for what the repo can't
  show, such as the product owner's decisions, the results of real runs, and pending manual steps. Those items are
  marked *(from the build conversation)*.
- **Where the repo is the source of truth:**
  - `CLAUDE.md` (rules and commands)
  - `docs/ROADMAP.md` (status)
  - `docs/PROGRESS.md` (session log)
  - `docs/ARCHITECTURE.md`
  - `docs/decisions/` (ADRs 0001–0009)

  When this document and the repo disagree, the repo wins. Note the disagreement.

---

## Executive summary

- **What it is.** StudySensei is a personal study planner and tutor: a React web app plus a FastAPI/Postgres back end.
  It is built around one loop: *know what's coming → decide what to study → study with support → check understanding →
  adjust*. Everything is grounded in the student's own course material. It replaces a retired PyQt webcam-focus
  prototype (git tag `v0-pyqt-prototype`).
- **Who it's for.** One local user for now: Joshua, the product owner. His COS330 Computer Security module (2026 S2) is
  the real test corpus. Multi-user beta is Phase 9.
- **Where it stands.**
  - Phases 0 and 1 are built and merged: foundations, then modules, topics, assessments, tasks, Today, study sessions
    with an event-log timer, the design system and session history.
  - Phase 2 (materials and topic maps) is mostly built. Merged so far: uploads and storage, the Postgres job worker,
    PDF/PPTX/DOCX/MD extraction, page-bound chunking with local embeddings and hybrid search, a free-tier LLM client
    (Gemini plus Groq), and AI topic maps with bounded cost and failure handling. That covers PRs #1–#21.
  - On COS330, all 21 eligible materials have been analysed into a 56-topic tree (Ch1–Ch13). That result is from the
    build conversation.
- **In flight.** The topic review screen (ROADMAP Phase 2 task 7, ADR 0009) is committed and pushed on branch
  `phase-2/topic-review`, 3 commits ahead of `main`. It is **not merged**. Its PR number and CI result are unknown to this
  document; the PR is probably #22.
- **Still open in Phase 2:**
  - the materials viewer (pdf.js, jump to page);
  - the AI provider settings page;
  - evals for topic extraction and search;
  - spike S1 (camera in the browser).

  Also outstanding: the Phase 1 real-use gate (real study days logged) has not been done.
- **Immediate next task.**
  1. Check CI on the topic-review PR, have Joshua merge it, and run migration 0014.
  2. Rebuild and review COS330's topic map, then record the review line for the "≥ 80 % kept" check.
  3. Then the next unchecked Phase 2 roadmap task: the **materials viewer** (pdf.js, jump to page). See §9.

---

## 1. What the project is

### Problem and goal

Students study from scattered slides, notes and past papers, and plan by gut feel. StudySensei's statement, from
`docs/PRODUCT.md`:

> *StudySensei tells you what to study next and why, helps you while you study it, and gets more accurate about you
> every week, using your own course material and your own study record.*

Modules, materials, the topic map, past-paper evidence, assessments and mastery form one shared context that every
feature reads. The camera and voice support study sessions; they are not the product.

### Users

- **Now:** a single local user, seeded as `local@studysensei.dev`. `get_current_user` returns them, and there is no
  login.
- **Later (Phase 9):** other students, with Supabase Auth, hosting and a POPIA review.
- Every table already carries `user_id`, and isolation is enforced as if multi-user.

### The student's journey (target; much of it not built yet)

The full version is in `docs/PRODUCT.md`.

1. **Onboarding:** add modules, import an outline, set availability, get a first plan.
2. **Module knowledge:** upload materials, review the AI topic map, see the past-paper profile.
3. **Today:** the next block and *why* it was chosen, reviews due, deadlines.
4. **Study session:** a timer with breaks, a side panel with materials and a cited tutor, and a 20-second reflection.
5. **Practice:** FSRS reviews and past-paper questions.
6. **Weekly review:** every insight is labelled *measured* or *estimated*, with its evidence.

### AI vs ordinary code (a core principle)

AI proposes topic maps, segments past papers, explains, answers, generates practice and writes up statistics.
**Ordinary code** does extraction, search, scheduling, statistics, timers and nudges. AI output is saved only after it
passes a Pydantic schema, and AI never changes the plan, timers or progress directly.

### Positions taken (deliberate scope exclusions, from `docs/PRODUCT.md`)

- No gaze-based "focus %".
- No emotion detection.
- The microphone is push-to-talk only.
- Voice is two-step: speech-to-text, then a streamed answer, then text-to-speech.
- No exam prediction. Only evidence and estimated emphasis from 3 or more papers.
- Rules and plain statistics come before any ML.
- Honest posture scope: deviation from the student's own baseline only.
- **AI costs nothing:** free tiers only, and no personal data in prompts.

---

## 2. Codebase and architecture

### Stack (verified in `package.json`, `apps/api/pyproject.toml`, `apps/web/package.json`)

| Layer | Choice |
| --- | --- |
| Web | React 19 + TypeScript (strict, `noUncheckedIndexedAccess`), Vite, Tailwind v4, shadcn/ui (restyled; components in `apps/web/src/ui/`), React Router 7, TanStack Query 5, Zustand, `openapi-fetch` (typed client), self-hosted Inter and Space Grotesk fonts |
| API | Python 3.12 (`>=3.12,<3.13`), FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2 async with **asyncpg**, Alembic, managed by **uv** |
| Documents | `pypdfium2` (PDF), `python-pptx`, `python-docx`. **PyMuPDF was rejected** (AGPL). `pikepdf` is a dev dependency, only for the password-protected test fixture |
| Search | Postgres full-text (`tsvector`, GIN) plus **pgvector** 384-dim embeddings from local **fastembed `BAAI/bge-small-en-v1.5`** (CPU) |
| Database | Postgres 16 + pgvector (`pgvector/pgvector:pg16`) in Docker, **host port 5433** |
| Jobs | A Postgres `jobs` table with `FOR UPDATE SKIP LOCKED`, and a separate worker process (no Redis) |
| AI | Our own `LLMClient` with one OpenAI-compatible adapter (httpx) for Gemini and Groq (free tiers), plus optional Ollama |
| Tests | pytest (real Postgres, `studysensei_test`), Vitest + Testing Library, Playwright e2e (own ports and DB) |
| CI | GitHub Actions `.github/workflows/ci.yml`, with jobs `api`, `web` and `e2e` |

### Runtime picture

```
Browser (React, :5173) ── /api/* (Vite proxy, same origin) ──► FastAPI (:8000) ──► Postgres+pgvector (:5433)
                                                                    ▲                 ▲
                                                 job worker (python -m app.jobs.worker) ┘
                                                    └─► Gemini / Groq (free tiers) via app/ai/
```

- `npm run dev` (`scripts/dev.mjs`) does the following in order:
  1. refuses to start if :8000 or :5173 is already answering (`scripts/ports.mjs`);
  2. starts Postgres (`docker compose up -d --wait db`);
  3. runs `alembic upgrade head` and seeds the local user;
  4. uses `concurrently --kill-others-on-fail` to run uvicorn (`--reload --reload-dir app`), the worker and Vite.
- The browser only ever calls `/api/*` on its own origin. Vite proxies that to `API_PROXY_TARGET` (default
  `http://localhost:8000`). This exists so a browser-driving agent can test the UI: the built-in browser blocks
  cross-port fetches.

### Repository layout (verified; 361 tracked files)

```
CLAUDE.md                     rules, commands, conventions, PR workflow, gotchas (read first)
README.md
.claude/settings.json         committed: allowlist + Stop hook (runs npm run check when the tree is dirty)
.claude/settings.local.json   personal, gitignored (see §6)
.github/workflows/ci.yml
docker-compose.yml            pgvector/pg16 on host 5433, volume db-data, init.sql creates studysensei_test
infra/db/init.sql
fixtures/session-timelines.json   shared event-log fixtures: pytest (timeline.py) AND vitest (timer.ts) run them
scripts/
  dev.mjs  ports.mjs  e2e.mjs  stop-check.mjs  with-lock.mjs (holds .locks/check.lock so two checks never overlap)
docs/
  PRODUCT.md  ARCHITECTURE.md  DESIGN.md  ROADMAP.md  PROGRESS.md  legacy-notes.md
  PLAN.md (frozen original plan; do not edit)  decisions/0001–0009
apps/api/
  app/main.py                 FastAPI app; routers: health, modules, topics, topic_maps, assessments, tasks,
                              sessions, materials, search, ai
  app/api/                    thin routers + deps.py (CurrentUser) + errors.py (NotFound/Conflict/Invalid → 404/409/422)
  app/core/config.py          ALL settings (pydantic-settings, reads apps/api/.env); AI routes/budgets live here
  app/core/db.py              async engine/session
  app/models/                 academics.py, sessions.py, materials.py, jobs.py, ai.py, topic_maps.py, user.py, base.py
  app/schemas/                Pydantic request/response + AI output schemas
  app/services/
    academics/                modules, topics (tree, move with cycle check), assessments, tasks
    sessions/                 sessions.py, timeline.py (pure event-log reducer)
    extraction.py             PDF/PPTX/DOCX/MD/TXT/image → pages
    filetypes.py              content-based upload validation
    materials.py
    search/                   chunking.py, embedding.py (fastembed / fake), indexing.py, search.py (RRF)
    topic_maps/               prompts.py, combine.py, merge.py, linking.py, review.py, __init__.py (status)
    ai_status.py  errors.py
  app/ai/                     client.py (LLMClient), adapter.py, routes.py, budget.py, usage.py,
                              sources.py (the ONLY way course text reaches prompts), messages.py, errors.py, ping.py
  app/jobs/                   queue.py (enqueue/claim/retry/reschedule), worker.py, kinds.py,
                              tasks/extract_text.py, index_material.py, extract_topics.py, merge_topics.py, link_topics.py
  app/storage/                base.py (Storage interface, key {user_id}/{sha256}), local.py (data/materials)
  app/seed.py                 seeds local@studysensei.dev
  alembic/versions/           0001–0014
  tests/                      academics/, ai/, api/, jobs/, materials/, search/, sessions/, topic_maps/, fixtures/
                              (synthetic PDF/PPTX/DOCX from make_fixtures.py, never course material), fakes.py (FakeLLM)
  evals/README.md             placeholder only: no evals exist yet
  scripts/export_openapi.py
apps/web/
  src/app/                    App, routes.tsx, AppLayout, TopNav (Today, Modules, Plan, Practice, Insights, Settings)
  src/features/today/         TodayPage, DeadlinesCard, CountdownTiles, DayTimeline, NextUpCard, SystemStatusCard
  src/features/modules/       ModulesPage, ModuleDetailPage (tabs: Assessments, Tasks, Topics, Materials, Sessions),
                              TopicTree, TopicMapPanel, ReviewBar, MergeTopicDialog, TopicPagesDialog, treeMoves.ts,
                              topicMap.ts, topicReview.ts, materials/ (MaterialsTab, MaterialSearch, PagesDialog, kinds,
                              status), assessments/, tasks/, sessions/ (SessionsTab, history)
  src/features/session/       SessionPage (/session, outside the nav layout), SessionProvider, controller.ts,
                              display.ts, ReflectionForm, AwayDialog, …
  src/session-engine/         timer.ts (pure), engine.ts, outbox.ts (offline queue), heartbeat.ts, store.ts, format.ts
  src/lib/api/                openapi.json + schema.d.ts (GENERATED by npm run gen:api), client.ts, errors.ts (unwrap/ApiError)
  src/ui/                     design-system primitives
  src/test/                   mockApi.ts, render.tsx, fakeSessionServer.ts, setup.ts
  e2e/                        materials.spec.ts, session.spec.ts (Playwright)
```

Plan, Practice, Insights and Settings are `PlaceholderPage` routes. They aren't built yet.

### API surface

The full, current list is in `docs/ARCHITECTURE.md` → "API contract". In summary:
- `GET /health` (DB check).
- **Modules and topics:**
  - `/modules`, `/modules/{id}`;
  - `/modules/{id}/topics` (a nested tree with `linked_pages`);
  - `/topics/{id}` and `/topics/{id}/move`.
  - Any edit makes an AI topic `source = user`.
- **Topic maps:**
  - `GET /modules/{id}/topic-map` (status) and `POST /modules/{id}/topic-map/build`;
  - `GET /modules/{id}/topic-map/materials` and `POST /materials/{id}/topics/retry`;
  - `DELETE /modules/{id}/ai-topics` (Clear AI topics).
  - **On `phase-2/topic-review` only (unmerged):**
    - `POST /topics/{id}/keep`, `/merge-into` and `/dismiss`;
    - `POST /modules/{id}/topics/keep-all`;
    - `GET /modules/{id}/dismissed-topics` and `POST /dismissed-topics/{id}/restore`;
    - `GET /topics/{id}/pages` and `DELETE /topics/{id}/pages/{material_id}/{page}`.
- **Assessments and tasks:** per-module lists, plus cross-module `GET /assessments?status=` and `GET /tasks?status=`
  (used by Today).
- **Sessions:**
  - `POST /sessions`, `GET /sessions/active`, `GET/DELETE /sessions/{id}`;
  - `POST /sessions/{id}/events` (idempotent batches) and `PUT /sessions/{id}/reflection`;
  - `GET /modules/{id}/sessions` (paged) and `GET /modules/{id}/sessions/summary`.
- **Materials:**
  - `POST /modules/{id}/materials` (multipart; 413/415/409) and `GET /modules/{id}/materials`;
  - `GET/PATCH/DELETE /materials/{id}` and `POST /materials/{id}/retry`;
  - `GET /materials/{id}/pages` and `GET /materials/{id}/pages/{n}`.
  - **There is no endpoint that serves the original file yet.** The viewer task needs one.
- **Search:** `GET /modules/{id}/search?q=&limit=8`.
- **AI:** `GET /ai/status` (keys set yes/no, roles, `used_today`/`daily_budget` per model).
- **Errors:** always `{"detail": ...}`. 404 also covers another user's row (deliberately indistinguishable). 409 is
  uniqueness, 422 is validation or a disallowed operation, and 503 is `AIUnavailable` (with `Retry-After`).

### Data model (verified table names; migrations `apps/api/alembic/versions/`)

| Migration | Tables / change |
| --- | --- |
| 0001 | `users`, `CREATE EXTENSION vector` |
| 0002 | `modules`, `topics` (tree via `parent_id`, `source` ai/user, `position`), `assessments`, `assessment_topics`, `tasks` |
| 0003 | `study_sessions`, `session_events` (PK `(user_id, id)`, server `seq`), `session_topic_ratings` |
| 0004 | data only: module colours mapped to the design-system swatches |
| 0005 | `materials`, `jobs` |
| 0006 | `material_pages` (+ queues extraction for existing materials) |
| 0007 | `chunks` (page number, position, text, token count, `embedding vector(384)`, generated `tsv`, GIN; **no vector index**) |
| 0008–0010 | `ai_usage` (+ `timeout` outcome, `vision` role) |
| 0011 | `topic_proposals`, `topic_pages`, `chunk_topics`; `long` role; `UNIQUE (id, module_id)` on chunks; queues `extract_topics` |
| 0012 | `ai_usage.job_id`, `ai_usage.detail`, `truncated` outcome |
| 0013 | `overloaded` and `refused` outcomes |
| 0014 *(branch only)* | `topic_reviews`, `topic_unlinks`, `too_large` outcome |

How tables relate:
- **Academic:** `modules` own `topics` (a tree), `assessments` (with `assessment_topics`) and `tasks`.
- **Materials:** `materials` (per module, `UNIQUE (module_id, sha256)`, `kind`, `status`, `allow_ai`) have
  `material_pages`, which have `chunks`. `chunk_topics` links chunks to topics.
- **Topic maps:**
  - `topic_proposals`: one per material.
  - `topic_pages`: the pages each topic was drawn from, which survive re-indexing.
  - `topic_reviews`: outlives the topic.
  - `topic_unlinks`: pages the student unlinked from a topic.
- **Sessions:** `study_sessions` have `session_events` and `session_topic_ratings`.
- **AI:** `ai_usage` holds per-call rows, never prompt or reply text.

**User isolation pattern** (must be followed for every new table; see ARCHITECTURE "User isolation"):
- `UNIQUE (id, user_id)` on user-owned tables.
- Children reference parents with **composite FKs** that include `user_id` or `module_id`.
- Join tables carry `module_id` with composite FKs to both sides.
- Services take a keyword-only `user_id` and filter every query on it.
- Another user's ID raises `NotFound`.
- `tests/test_schema_guards.py` fails if a new table lacks `user_id` without being allow-listed.
- Every endpoint gets an HTTP cross-user test in `tests/api/test_cross_user_api.py`.

### Background pipeline (job kinds in `app/jobs/kinds.py`)

`upload` → `extract_text` → `index_material` → (`extract_topics` per eligible material) → `merge_topics` → `link_topics`.

- **Statuses:** a material is `uploaded`, then `processing`, then `ready`. "Ready" means it is searchable.
- **Retries:** jobs retry after 30 s, 2 min and 8 min (`max_attempts` 3, capped at 30 min). Stale locks over 10 min
  are reclaimed.
- **Rescheduling:** `AIUnavailable` reschedules a job without using an attempt (`queue.reschedule`).
- **Extraction:** a "scanned" page has fewer than 20 non-space characters. The text of scanned pages is **not
  transcribed yet**; that's the future opt-in vision step.
- **Chunks:**
  - at most 400 tokens, counted with bge's tokenizer;
  - never across pages;
  - ~50 tokens of overlap;
  - the embedded text is prefixed "material title · page title".
- **Topic-map eligibility:** `allow_ai` is on and the kind is slides, notes, study_guide, tutorial or outline. Past
  papers, tests and assignments are excluded; Phase 6 handles them.

### AI layer (`app/ai/`, ADRs 0002, 0007, 0008, 0009)

- **Interface:** `complete_text(role, messages, *, purpose, user_id, reasoning_effort=None)` and
  `complete_json(role, messages, Schema, …)`. JSON replies get one repair turn at most.
- **Roles** (config defaults in `app/core/config.py`, overridable by env as JSON lists):

  | Role | Order (each at `low` unless noted) | Use |
  | --- | --- | --- |
  | `smart` | Groq `openai/gpt-oss-120b` → `gemini-3.5-flash-lite` → `gemini-3.8-flash` | tutor (future) |
  | `bulk` | `gemini-3.5-flash-lite` (`minimal`) → Groq `openai/gpt-oss-20b` | classification, tagging |
  | `vision` | `gemini-3.5-flash-lite` → Groq `qwen/qwen3.8-27b` → `gemini-3.8-flash` | any message with an image |
  | `long` | `gemini-3.5-flash-lite` → `gemini-3.8-flash` → Groq `openai/gpt-oss-120b` | whole documents: topic extraction and merge |

- **Daily budgets** (requests): 3.8 Flash 18, Flash-Lite 450, Groq models 900 each.
  - Gemini quotas reset at midnight Pacific; Groq's are assumed to reset at midnight UTC.
  - Pacing per minute: Flash-Lite 12, 3.8 Flash 4, Groq 25.
  - These are estimates. Google no longer publishes free-tier numbers.
- **Thinking levels:** `gemini-3.8-flash` has **no `minimal`**, so asking for it is a 400.
  `routes.wire_effort` raises an unsupported level to the model's lowest supported one.
- **Failure rules:**
  - **Moves on to the next model:** 429, 503 (`overloaded`), timeout, lost connection, 413 (`too_large`) and content
    refusal (`refused`).
  - **Waits, raising `AIUnavailable`:** any other persistent 5xx.
  - **Fails loudly, raising `AIRequestFailed`:** other 4xx.
  - Invalid output is repaired once and never moves to another model.
  - `finish_reason=length` raises `AITruncated`.
  - Topic jobs: at most 4 counted calls per material per run (`TOPIC_MAX_CALLS`). Turned-away 429/503/413 requests have
    their own cap of 20 (`TOPIC_MAX_TURNED_AWAY`).
- **Privacy:**
  - Course text reaches prompts only via `app/ai/sources.py`, which filters `allow_ai = true` and never sends file names.
  - No names, emails, student numbers or reflections go in prompts.
  - Keys are `SecretStr`, are never logged, and `/ai/status` only says yes or no.
- **Tests never hit a provider.** `tests/conftest.py` blanks the keys and installs a failing transport, and `FakeLLM`
  scripts the replies.
- **Ping:** `uv run --directory apps/api python -m app.ai.ping`.

### Web app patterns

- **Server calls:** only through `api` in `src/lib/api/client.ts`. The types are generated; never hand-write them.
  Hooks live in `features/<area>/api.ts` and use `unwrap()`.
- **State:** server state lives in TanStack Query. Zustand holds only client state that must outlive a component.
- **Timer:** pure functions of the event log and an injected `now`. The same JSON fixtures as the server run against
  it. There's an offline outbox in localStorage, a 15 s heartbeat, and an "away" question for gaps over 2 minutes.
- **Visual design:** `docs/DESIGN.md`, direction **B "Planner"**.
  - Ink #111111 on paper #FFFFFF, Space Grotesk headings and Inter body.
  - 2 px borders, radius 4–6, no shadows, top navigation.
  - Module colours are fills behind ink text only.

---

## 3. Completed work

Status keys:
- **Verified:** merged, CI green, *and* checked with real use or data.
- **Tested:** merged with automated tests and green CI, but not checked in real use.
- **Partial:** started but not finished.
- **Branch:** implemented on an unmerged branch.
- **Planned:** not started.

| # | Feature (PRs) | What and why | Key files | Status |
| --- | --- | --- | --- | --- |
| 0 | Foundations (#1) | Monorepo, Docker Postgres, FastAPI `/health`, Vite shell, CI, Stop hook, docs. The PyQt app was retired (ADR 0001) because it didn't install, sessions died after 60 s, and its metrics were wrong | `scripts/`, `.github/`, `CLAUDE.md` | Verified |
| 1.1 | Academic models + user isolation (#2) | modules, topics tree, assessments, tasks with composite-FK isolation | `models/academics.py`, `tests/academics/` | Tested |
| 1.2 | Modules/topics endpoints + UI (#3) | CRUD, manual topic tree with move and cycle check | `services/academics/topics.py`, `features/modules/` | Verified (clicked through) |
| 1.3 | Assessments + tasks (#4, #5) | Dates (timezone required), weight, topic scope | `services/academics/` | Verified (clicked through) |
| 1.4 | Today page (#6) | Upcoming deadlines, countdowns, honest empty states (no plan yet) | `features/today/` | Tested |
| 1.5 | Study sessions + events (#7) | Append-only event log, pure replay, idempotent offline batches (ADR 0003) | `services/sessions/timeline.py` | Tested |
| 1.6 | Timer engine (#8) | Pure `timer.ts`, offline outbox, heartbeat and away detection; shared fixtures with the server | `src/session-engine/` | Tested |
| 1.7 | Design system v1 "Planner" (#9) | Tokens and components restyled; module colour migration 0004 | `docs/DESIGN.md`, `src/ui/`, `index.css` | Tested; full visual review pending |
| 1.8 | Session screen (#10) | Timer UI, breaks, end, 20-second reflection | `features/session/` | Tested (e2e); **real-use gate not done** |
| 1.9 | Session history (#11) | Paged history and weekly summary per module | `features/modules/sessions/` | Tested |
| 2.1 | Uploads, storage, job worker (#12) | Content-hash storage, type checks, 50 MB limit, Postgres job queue (ADR 0004) | `storage/`, `jobs/`, `services/filetypes.py` | Verified (29 real COS330 files) |
| 2.2 | Text extraction (#13) | Per-page text, scanned-page flag, readable failures | `services/extraction.py` | Verified (CH02/CH05 "scanned" pages are image-only figures; ST1 2012/2016/2018/2020 scans flagged) |
| 2.3 | Chunking + local embeddings + hybrid search (#14) | Page-bound ≤ 400-token chunks, bge-small, exact vector scan plus FTS fused with RRF (ADR 0005); search box on the Materials tab | `services/search/`, `MaterialSearch.tsx` | Verified (11 of 12 real queries had the right page first; the miss had no relevant material at the time) |
| 2.4 | LLM client (#15–#18) | One adapter; roles, budgets, pacing, timeouts, thinking levels, provider error text, vision role, ping CLI | `app/ai/` | Verified (real ping: Groq ~0.3–0.6 s, Flash-Lite ~1 s, 3.8 Flash overloaded or timing out) |
| 2.5 | AI topic maps (#19–#21) | Per-material proposals, anchored merge, local linking; bounded cost, lenient parsing, 503/refusal handling (ADRs 0006–0008); Clear AI topics; per-material topic status and retry | `services/topic_maps/`, `jobs/tasks/*topics*` | Verified on COS330: 56-topic tree. The first run used ~155 calls; after the fixes a rebuild used ~15 |
| 2.6 | Topic review screen (branch `phase-2/topic-review`) | Keep, Rename, Merge into, Dismiss (remembered), Restore, Keep all; linked-pages panel with Unlink; review stats; compact merge input so Groq can merge (ADR 0009) | `services/topic_maps/review.py`, `ReviewBar.tsx`, `MergeTopicDialog.tsx`, `TopicPagesDialog.tsx`, migration 0014 | **Branch:** CI and merge status unknown here; not used on real data |
| 2.7 | Materials viewer (pdf.js, jump to page) | Upload UI with processing status and module search already exist; the pdf.js viewer and a file-serving endpoint do not | n/a | **Partial / Planned** |
| 2.8 | AI provider settings page | Settings is still a placeholder; `/ai/status` exists | n/a | Planned |
| 2.9 | Evals (`topic_extraction`, `search`) | `apps/api/evals/` holds only a README | n/a | Planned |
| S1 | Spike: camera in the browser | Background-tab throttling: Worker + `MediaStreamTrackProcessor`, Document PiP, Tauri fallback | n/a | Planned (not started) |
| S3 | Spike: visual direction | Three directions explored; **B "Planner" chosen 13 Nov** | design canvas artifact | Done, but the ROADMAP checkbox is still unticked |

**Removed or superseded:**
- The entire PyQt app. It's recoverable with `git show v0-pyqt-prototype:<path>`, and reusable ideas are in
  `docs/legacy-notes.md`.
- The original plan's Anthropic adapter (ADR 0002).
- "Gemini 3.8 Flash as the primary smart model" (superseded 17 Nov by the rebalanced routes).
- The 400–800-token chunk plan (ADR 0005).

**Real COS330 results** *(from the build conversation; the dev DB is Joshua's local Docker volume)*:
- **Uploaded (29 materials):**
  - 12 slide decks (CH01–CH11, CH13), re-uploaded with kind Slides;
  - 8 ST1 past papers (kind Past paper);
  - chapter notes: Ch1–6 as `.md` and Ch7–8 as `.docx` (8 files; the duplicate `.docx` for Ch5/Ch6 was deleted);
  - the Final Study Guide.
- **Not uploaded:** the owner's own submissions, the 34 MB textbook, the zips and the `2024 Exam`/`P4` folders.
- **Topic tree:** Ch1 Overview, Ch2 Cryptographic tools and Ch3 User authentication are the student's own anchors.
  Ch4 Access Control through Ch13 Cloud Computing and IoT Security are AI topics, each with 3–6 subtopics; Ch9
  Firewalls is its own chapter.
- **Last known state (17 Nov ~21:10):**
  - 21 of 21 materials analysed.
  - A final merge, which adds topics from the Ch1/5/7 notes, was being rescheduled repeatedly because Gemini returned
    503s. Its outcome is **unknown**.

---

## 4. Current development position

- **Phase:** 2 (Materials and topic maps).
- **Latest merged:** PR #21 (`phase-2/topic-refusals`), 17 Nov 20:53, merge commit `227500b`.
- **Latest work:** branch `phase-2/topic-review`, HEAD `a0541fd` ("docs: ADR 0009 topic review; ARCHITECTURE, ROADMAP
  and PROGRESS"). It is pushed to `origin` (its remote-tracking ref matches), with a clean working tree.
- **Unverified here:** whether a PR is open for it, and its CI result. Check with `gh pr list` and `gh pr checks <n>`.
- **The branch ticks** "Topic review UI" in ROADMAP. Remaining unchecked in Phase 2:
  1. Upload UI with processing status, materials viewer (pdf.js, jump to page) and module search
  2. AI provider settings page
  3. `evals/topic_extraction` and `evals/search` from COS330
- **Phase 2 verify/done criteria still to demonstrate:**
  - 12 of 15 hand-written queries have the right slide in the top 3 (needs `evals/search`);
  - **at least 80 % of proposed topics kept with small edits** (read off the review line after a real review);
  - a module with 3 or more decks gets a map in about 3 minutes;
  - every AI call is in `ai_usage` (true by design).
- **Phase 1 gate (not done):**
  - a real 50-minute session with one reload and one break, timer within 1 s of a clock;
  - three real study days logged;
  - review of real use in the Project chat.
- **Blockers:** none in code. The free-tier AI capacity is the main external constraint:
  - Gemini 503s in the evening;
  - 3.8 Flash's ~20 requests a day;
  - Groq's 8K tokens a minute.

### Known issues and limitations (verified in code or docs unless marked)

1. **Unmerged review branch.** Migration 0014 isn't on `main`, so Joshua's dev DB won't have it until he merges the
   branch and restarts `npm run dev`.
2. **Unvalidated similarity threshold.** The cut-off is 0.63 (`TOPIC_LINK_THRESHOLD`, top 12), calibrated on synthetic
   text with a thin margin (0.63–0.90 related vs 0.41–0.62 unrelated). Re-check it on COS330 in the evals task.
3. **Scanned pages have no text yet.** Full scans (ST1 2012, 2016, 2018, 2020) and figure slides contribute nothing to
   search or topics until the opt-in vision transcription exists (ROADMAP Phase 6; the `vision` role is ready).
4. **Free-tier numbers are estimates.**
   - Budgets in `config.py` come from 429 replies and AI Studio, not published docs.
   - Gemini 3.8 Flash is often overloaded and allows ~20 requests a day, so it's a last resort only.
   - Groq rejects requests over its 8K tokens a minute (a 413, which moves on).
5. **Merge depends on Gemini.** On `main`, the merge input is too large for Groq. The branch's compact input (≤ 7,000
   estimated tokens, ADR 0009) is the fix.
6. **Open sessions never auto-close** if the client never ends them (ADR 0003 consequence).
7. **No file-serving endpoint** for materials, which the pdf.js viewer needs.
8. **Placeholder pages:** Plan, Practice, Insights and Settings.
9. **Documentation inconsistencies found during this review** (low risk; fix in a docs PR):
   - ROADMAP spike **S3** is unticked although direction B was chosen and implemented.
   - ARCHITECTURE's role table says `smart` is for "tutor, topic maps", but topic maps use the `long` role.
   - ARCHITECTURE's "Data model" table has a misaligned "Topic maps" row: the `materials.kind`/status notes landed in
     it.
   - ARCHITECTURE's repository layout says `scripts/dev.mjs` runs "api + web" and omits the worker.
   - PROGRESS has an entry dated **2026-11-18** ("topic map fixes"); it was written on 17 Nov.
   - ADR 0002 carries two "Update, 2026-11-17" sections. CLAUDE.md says ADRs are never edited and get superseded
     instead; these were added at the product owner's request.
   - CLAUDE.md says "use plan mode for anything touching more than a couple of files". In practice, task prompts that
     are fully specified say "skip plan mode", and that has worked.
10. **No `jq` in Claude Code's shell** (from its PR #20 report). Use `gh pr checks --watch` without jq.

---

## 5. Decisions and context

**Do not reverse these without understanding the reason and asking Joshua.**

### Architecture decision records (`docs/decisions/`)

| ADR | Decision | Why |
| --- | --- | --- |
| 0001 | Rebuild as a web app (React/Vite + FastAPI + Postgres/pgvector). Camera and voice in the browser. Monorepo | The PyQt prototype didn't install, sessions died, metrics were wrong, and it was hard to polish. Python suits document/ML work, and Pydantic validates AI output. One Postgres for relational data, vectors, FTS and jobs. Tauri stays the fallback if spike S1 fails |
| 0002 | Free-tier AI only (Gemini + Groq, optional Ollama) behind one OpenAI-compatible adapter. No Anthropic adapter. No personal data in prompts | The product owner said "AI must cost nothing". Free-tier prompts may be used by the provider. LiteLLM/LangChain are too heavy for ~200 lines. Updated 17 Nov with real model IDs and limits, then rebalanced routes after real pings |
| 0003 | Study sessions are an append-only event log; totals are derived by one pure reducer; events are idempotent with client UUIDs; one open session per user | A browser timer gets reloaded, throttled or goes offline; client-sent durations can't be audited |
| 0004 | Store files by `{user_id}/{sha256}` behind a `Storage` interface; Postgres job queue with `SKIP LOCKED` | Dedupe re-uploads, never share across users, and no Redis; jobs are transactional with data |
| 0005 | Chunks are page-bound and ≤ 400 tokens (bge-small reads 512). Local bge-small embeddings; exact vector scan (no HNSW yet) + FTS with RRF k = 60; snippets as parts, never HTML | Citations must point at one page. HNSW with filters can under-return. Add HNSW when a module's scan costs > ~50 ms (~50–100k chunks) or at multi-user scale |
| 0006 | Topic maps: per-material proposals, then one anchored merge applied by code (additions only); `topic_pages` keeps citations; linking by cited pages + local similarity | AI can't be trusted to keep the student's topics. Per-material extraction survives failures and re-uploads. No per-chunk AI calls (quota) |
| 0007 | Bounded extraction: lenient parsing, ≤ 4 calls and 1 repair per material per run, ~40-page parts, per-minute pacing, stricter "move on" rules | The first COS330 run cascaded through fallbacks: ~155 calls where ~22 were needed |
| 0008 | 503 = `overloaded` and content refusal = `refused` both move on; 429/503 don't count toward the cap (they have their own cap of 20); names accepted from `title`/`topic`/`heading`/`label` | The remaining 3 failures were Gemini 503s and a name-key mismatch, not safety refusals |
| 0009 *(branch)* | Compact merge input (≤ 7,000 estimated tokens); 413 = `too_large` moves on; review actions; `topic_reviews` outlives topics; dismissed names are blocked in code; unlinks remembered | Lets Groq do the merge when Gemini is busy; the student's review always wins; makes the 80 % check measurable |

### Other established decisions *(from the build conversation unless the repo also says so)*

- **Test corpus: COS330.** It lives at a local folder (its path is in `CLAUDE.local.md`, which isn't committed) and is
  read-only. Never copy it into the repo, use it as test fixtures, or commit it. The student's own
  submissions are never uploaded or sent to AI. (CLAUDE.md agrees.)
- **AI providers.** Joshua has free keys for Gemini (AI Studio) and Groq in `apps/api/.env`. Groq gpt-oss-120b leads the
  `smart` role because Gemini 3.8 Flash's free tier was too slow and too limited (two 30 s timeouts, ~20 requests a
  day, 503 "high demand").
- **For the future tutor (Phase 3):** an *interactive* call should move straight on from a 503 rather than wait.
  Background jobs may wait. A bad key (401) should still fail visibly.
- **Visual direction B "Planner"** was chosen 13 Nov from three directions on the design canvas.
- **Rejected approaches:**
  - PyMuPDF (AGPL) and Docling (PyTorch).
  - Tesseract for scans (weak on maths and handwriting).
  - Redis/Celery.
  - A hosted embedding API (course text would leave the machine).
  - bge-base (3–4× slower on a laptop CPU).
  - Letting the AI rewrite the topic tree.
  - Per-chunk AI classification.
  - Strict `json_schema` response format (not consistent across providers).
- **Workflow.**
  - Claude Code implements one roadmap task per branch and PR. It pushes, opens the PR and watches CI itself, and it
    **never merges** and never pushes to main.
  - Joshua merges.
  - The Project chat writes the Claude Code prompts, reviews reports and PRs, and checks results in the built-in
    browser.
- **Don't run the app while Claude Code edits it.** Joshua runs `npm run dev` in his own terminal and **stops it while
  Claude Code works**, because they share one working tree. Half-finished code and migrations otherwise hit the running
  app, and restarting would apply an unfinished migration to the dev DB. The Docker database keeps running after
  Ctrl+C, so Claude Code can still query it with `docker compose exec db psql -U studysensei -d studysensei`.
- **Test before merging when AI quality matters.** For AI-quality features, run on real data before merging (as was
  done for PR #13 and the topic maps).

---

## 6. Development environment and tooling

### Machine *(from the build conversation and device info)*

- **OS and shell:** Windows; repo at `C:\StudySensei`; PowerShell.
- **Tools:**
  - Docker Desktop (Postgres container `studysensei-db-1`).
  - `uv`, installed via scoop (Python 3.12 lives under the user's scoop folder).
  - Node LTS.
  - VS Code with the **Claude Code extension in Auto mode**.
- **WSL:** not otherwise used. Once, a background dev server started by Claude Code was killed for low memory; capping
  WSL memory with `.wslconfig` (`memory=4GB`) was suggested. Whether it was applied is **unknown**.

### First-time setup (repo root)

```
npm install                      # root + apps/web
npx playwright install chromium  # for e2e
cd apps/api && uv sync && cd ../..
copy apps\api\.env.example apps\api\.env   # then add GEMINI_API_KEY / GROQ_API_KEY
npm run dev                      # db → migrate → seed → api :8000 + worker + web :5173
```

The first indexing run downloads the embedding model (~65 MB) to `data/models`.

### Everyday commands (verified in `package.json` and CLAUDE.md)

| Command | What |
| --- | --- |
| `npm run dev` | Full stack (refuses if :8000 or :5173 is busy) |
| `npm run check` | ruff (lint + format check), prettier, eslint, mypy `--strict`, tsc, pytest, vitest; holds `.locks/check.lock` |
| `npm run check:steps` | The same, without the lock |
| `npm run e2e` | Playwright on API :8001, web :5174, DB `studysensei_e2e` (rebuilt each run) |
| `npm run format` | ruff format + fix, prettier |
| `npm run gen:api` | Export OpenAPI and regenerate `schema.d.ts`. Run after any API schema change; CI fails if stale |
| `npm run db:up` / `db:down` / `db:migrate` / `db:seed` | Postgres only, migrations, seed |
| `uv run --directory apps/api pytest -k <expr>` | Some API tests |
| `uv run --directory apps/api alembic revision --autogenerate -m "…"` | New migration (check the file it writes; never edit merged migrations) |
| `uv run --directory apps/api python -m app.jobs.worker` | Worker alone |
| `uv run --directory apps/api python -m app.ai.ping` | Check AI keys and models |
| `uv run --directory apps/api python -m tests.fixtures.make_fixtures` | Regenerate synthetic test documents |
| `npm run test:watch -w apps/web` / `npm run build -w apps/web` | Web only |

### Databases

Postgres runs on `localhost:5433`; user, password and db are all `studysensei`.
- `studysensei`: dev.
- `studysensei_test`: pytest. The conftest refuses any DB not ending in `_test`, because it runs downgrade and upgrade.
- `studysensei_e2e`: Playwright.

### Environment variables

In `apps/api/.env`, which is gitignored and documented in `apps/api/.env.example`. Never commit real values.

```
DATABASE_URL=postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei
CORS_ORIGINS=["http://localhost:5173"]
GEMINI_API_KEY=<your Gemini key>
GROQ_API_KEY=<your Groq key>
# optional: OLLAMA_MODEL, STORAGE_DIR, MODELS_DIR, AI_SMART/AI_BULK/AI_VISION/AI_LONG (JSON route lists),
# AI_DAILY_BUDGET, AI_REQUESTS_PER_MINUTE, AI_REASONING_EFFORTS, AI_QUOTA_TIMEZONE, AI_*_TIMEOUT_SECONDS,
# TOPIC_MAX_CHARS, TOPIC_LINK_THRESHOLD, TOPIC_LINK_MAX_CHUNKS, TOPIC_PART_PAGES, TOPIC_MAX_CALLS,
# TOPIC_MAX_TURNED_AWAY, TOPIC_MERGE_MAX_TOKENS
```

`apps/web/.env` is optional: `VITE_API_URL`, or `API_PROXY_TARGET` for the dev proxy.

### Git workflow

- **Remote:** `origin` = `https://github.com/Josh-Heath123/StudySensei.git`. `main` is the default branch.
- **Branches:** `phase-N/<task>`. Old task branches remain locally; `rebuild` was the Phase 0 branch.
- **Commits:** small, conventional (`feat(api): …`, `fix(web): …`, `docs: …`, `ci: …`, `chore: …`).
- **Finishing a task:** `npm run check` green, tick ROADMAP, add a PROGRESS entry, and update ARCHITECTURE/PRODUCT in
  the same PR when they change.
- **Archive tag:** `v0-pyqt-prototype`.

### Claude Code configuration (verified)

- **Project instructions:** `CLAUDE.md`.
- **`.claude/settings.json` (committed):**
  - **Allowlist:** `uv run`, `npm run`, `git status/diff/log/add/commit`.
  - **Stop hook:** `node scripts/stop-check.mjs`, timeout 1500 s. It runs `npm run check` when `git status --porcelain`
    shows changes, blocks once on failure, then lets the session stop with a warning.
- **`.claude/settings.local.json` (personal, gitignored):**
  - `additionalDirectories` gives access to the COS330 folder.
  - 46 allow rules: uv, npm, docker compose, git read/add/commit/switch/pull/fetch, pushing `phase-*` branches, and
    `gh pr …` and `gh run …` commands.
  - Denies: force pushes, pushes to main, branch deletes, `reset --hard`, `git clean`, `gh pr merge`, `gh repo delete`,
    and reading `.env` anywhere.
- **No custom agents, skills or slash commands** exist in the repo (`.claude/` holds only the two settings files).

### The claude.ai Project chat setup *(from the build conversation)*

- **Device bridge:** the Project chat reaches `C:\StudySensei` and the COS330 folder through the device bridge, which
  appear as `$HOME/mnt/StudySensei` and `$HOME/mnt/COS330` in the bridge shell.
  - Use read-only git there with `GIT_OPTIONAL_LOCKS=0`.
  - Deletes are blocked by default.
  - The bridge VM can't reach `localhost` services or authenticate to GitHub.
- **Built-in browser:** `http://localhost:5173` and `http://127.0.0.1:5173` are approved, so the chat can drive the app
  and call `/api/*` through the dev proxy with in-page `fetch`.
  - Typing into a hidden pane is unreliable, so prefer API calls via JavaScript.
  - Keep scripts short (calls time out at 45 s).
- **Project doc** `claude/studysensei-status.md`: a short status summary, kept current by the chat.
- **Artifacts:**
  - Full plan: https://claude.ai/artifact/6MVgWsfQXpGkdgwYvc7PZC (frozen copy in `docs/PLAN.md`).
  - Design canvas: https://claude.ai/artifact/VRuYrxfbGF65SRyfiAfqyd

---

## 7. Testing, quality and known issues

- **API (pytest, real Postgres):**
  - user scoping and cross-user HTTP tests for every endpoint;
  - shared timeline fixtures;
  - extraction on synthetic fixtures (including an image-only page and a password-protected PDF);
  - chunking, RRF and search;
  - AI client behaviour with `FakeLLM` and fake transports (429/503/413, refusals, budgets, pacing, truncation,
    timeouts);
  - topic-map extraction, merge anchoring, linking, review, and migration tests;
  - two `real_embedder`-marked tests that use the real bge model (cached in CI);
  - a schema guard for `user_id`.
- **Web (Vitest + Testing Library):** component and logic tests next to the code, with the API stubbed via `mockApi`.
  The timer engine is tested with an injected clock against the shared fixtures.
- **E2E (Playwright):** `session.spec.ts` (with the browser clock installed and paused) and `materials.spec.ts`, both
  against the real stack.
- **Reported results** (from Claude Code reports relayed in the build conversation; not re-run for this document):
  - PR #21: `npm run check` passed locally with **537 API and 271 web tests**, and CI api/web/e2e were green before
    merge.
  - Static count in the tree now: about 382 pytest test functions (parametrised cases add more) and about 214 web
    `it`/`test` calls.
  - **The topic-review branch's test and CI results are not known here.**
- **Failing tests:** none known on `main`.
- **Quality bar (CLAUDE.md):**
  - `mypy --strict`, ruff at line length 100, strict TypeScript, prettier and eslint, all in CI.
  - Timer, planner, mastery, metric and signal code is merged only with unit tests.
  - Every number shown to the student is labelled measured or estimated, with its sample size.
- **Definition of done** (CLAUDE.md "Finish every task"):
  - `npm run check` green;
  - ROADMAP ticked;
  - a PROGRESS entry;
  - the PR pushed with CI green;
  - for AI features, also a run on real COS330 data reviewed in the Project chat.
- **Security and privacy requirements:**
  - Every query is scoped by `user_id` (enforced in services *and* by composite FKs).
  - No secrets in git.
  - Uploads are validated by content.
  - Course text is untrusted in prompts (wrapped in `<material>` tags, with a system instruction not to follow it).
  - Camera frames and audio never leave the browser (Phase 7).
  - No personal data in AI prompts.
- **Needs verification before more building:**
  1. The topic-review PR's CI.
  2. Migration 0014 applied in dev.
  3. A real review of COS330's map, recording the 80 % check.
  4. Whether the 17 Nov evening merge completed. If not, click "Build topic map".

---

## 8. Git and repository state (inspected 17 Nov 2026, ~21:45 SAST)

| Item | Value |
| --- | --- |
| Current branch | `phase-2/topic-review` |
| HEAD | `a0541fd9ae7dd9bb436a054d943fc243bee27885` (2026-11-17 21:38:44 +0200) "docs: ADR 0009 topic review; ARCHITECTURE, ROADMAP and PROGRESS" |
| Upstream | `origin/phase-2/topic-review` |
| Relative to `origin/main` | 3 commits ahead, 0 behind (from local remote-tracking refs; `git fetch` wasn't possible from the inspection VM, so refs may be stale) |
| Uncommitted / staged changes | None (clean). This handover file is the only addition, and it is **untracked** |
| `main` / `origin/main` | `227500b` Merge PR #21 (`phase-2/topic-refusals`), 2026-11-17 20:53 |
| Tags | `v0-pyqt-prototype` |
| Merged PRs on main | #1 rebuild · #2 models · #3 modules-ui · #4, #5 assessments · #6 today · #7 study-sessions · #8 timer · #9 design-system · #10 session-screen · #11 session-history · #12 materials-and-jobs · #13 text-extraction · #14 chunking-search · #15 llm-client · #16 llm-client-timeouts · #17 llm-effort-levels · #18 rebalance-ai-routes · #19 topic-maps · #20 topic-map-fixes · #21 topic-refusals |

**Work to preserve:**
- `phase-2/topic-review`: pushed, but not merged.
- `apps/api/.env` holds the keys. It's local only and must never be committed.
- `data/` (uploads and model cache, gitignored) and the Docker volume `db-data` hold Joshua's COS330 data.

**This file:** `docs/PROJECT_HANDOVER.md` was written while `phase-2/topic-review` was checked out. Commit it on purpose,
for example in its own small `docs: project handover` PR, or keep it untracked. Don't let a feature PR sweep it in by
accident.

---

## 9. Immediate development handover

### First, inspect (about 10 minutes)

1. Read `CLAUDE.md`, then the top of `docs/PROGRESS.md`, then Phase 2 in `docs/ROADMAP.md`.
2. Check git and PR state:
   ```
   git status
   git branch --show-current
   git log --oneline -5
   gh pr list
   gh pr checks <n>
   ```
   Is `phase-2/topic-review` still unmerged? Is its CI green?
3. Skim ADR 0009 and `apps/api/app/services/topic_maps/review.py` before touching topic code.
4. If you're the Project chat: check whether the app answers at `localhost:5173`. If it does, read
   `GET /api/modules/{COS330 id}/topic-map` and `GET /api/ai/status`.

### Then, in order

1. **Close out the topic review (task 7).**
   - If the PR's CI is green, Joshua merges it. Then `git switch main`, `git pull` and `npm run dev`, which applies
     migration 0014.
   - On COS330's Topics tab:
     1. If the last merge never finished, click **Build topic map**. With the compact input, Groq can now take it.
     2. Turn on the **Review** filter.
     3. Joshua reviews: Keep, Rename, Merge, Dismiss. Open a few topics' linked pages and unlink wrong ones.
   - Record the review line ("Review: N kept, N renamed, N merged, N dismissed") in PROGRESS or the status doc. That is
     the Phase 2 "≥ 80 % kept with small edits" check.
   - Also note how many linked pages were wrong. That feeds the 0.63 threshold check.
2. **Next roadmap task: "Upload UI with processing status, materials viewer (pdf.js, jump to page) and module search".**
   - **Why next:** it's the next unchecked Phase 2 task in ROADMAP order. Search results, topic linked pages and (in
     Phase 3) tutor citations all need "open this exact page". PROGRESS's last entry suggests the AI settings page
     next, which is a reasonable alternative. Confirm with Joshua if unsure, and default to ROADMAP order.
   - **Already exists, so don't rebuild it:**
     - upload with live processing status and per-material topic status (`MaterialsTab.tsx`);
     - search (`MaterialSearch.tsx`, `GET /modules/{id}/search`);
     - a plain page-text dialog (`PagesDialog.tsx`, `GET /materials/{id}/pages/{n}`);
     - the topic linked-pages panel (`TopicPagesDialog.tsx`, on the review branch).
   - **Missing:**
     - a user-scoped file endpoint, for example `GET /materials/{id}/file`, that streams the stored blob (via `Storage`,
       key `{user_id}/{sha256}`) with the right content type and `Content-Disposition: inline`, returns 404 for other
       users, and has a cross-user test;
     - a pdf.js viewer (`pdfjs-dist`, Apache-2.0) with page navigation and jump-to-page;
     - wiring so search results and linked pages open the viewer at the right page (falling back to the text view for
       PPTX, DOCX and MD);
     - a polish pass on the processing-status UI.
   - **Likely files:**
     - `apps/api/app/api/materials.py`, `app/services/materials.py`, `app/storage/`;
     - `apps/web/src/features/modules/materials/` (a new viewer component) and `TopicPagesDialog.tsx`;
     - `npm run gen:api`;
     - tests in `tests/api/test_materials_api.py` and `test_cross_user_api.py`;
     - a Playwright step in `materials.spec.ts`.
   - **Verify:**
     - `npm run check` and `npm run e2e` green;
     - in the browser, a search for "inference channel" opens CH05 at the right page;
     - a topic's linked page opens at that page;
     - a scanned ST1 page renders as an image.
3. **AI provider settings page.** The Settings route is a placeholder. Show `/ai/status`: which keys are set (never the
   key), the role order, today's usage against the budget, and when quotas reset. Add a "Test keys" button using the
   ping logic. Keys stay in `.env` until Phase 9 adds encrypted per-user keys.
4. **Evals.**
   - `apps/api/evals/search`: 15 hand-written COS330 queries with expected material and page. Target: 12 of 15 in the
     top 3.
   - `apps/api/evals/topic_extraction`: compare against Joshua's reviewed tree.
   - Commit only queries, expected answers and page refs, never course text (`apps/api/evals/README.md`).
   - Re-check the 0.63 linking threshold here.
5. **In parallel or after:** spike S1 (camera in the browser); the Phase 1 real-use gate (Joshua studies with the timer
   for three days); a small docs PR fixing the inconsistencies in §4.9.
6. **Then Phase 3 (tutor and voice):**
   - Retrieval with a current-topic boost.
   - An SSE tutor with [S1]–[S8] citations into the viewer.
   - Remember the interactive-503 rule from §5.

### How Claude Code tasks are run

Each task is one prompt pasted into Claude Code. The prompt should:
- name the branch base ("new branch from main");
- give a concrete spec;
- say whether to skip plan mode;
- end with "take it straight to a green PR".

Claude Code then works through CLAUDE.md's PR steps. Joshua pastes its report back to the Project chat, and the chat
reviews it (reading the diff via the bridge, and testing in the browser when the app is running) before telling Joshua
to merge.

---

## 10. Instructions for the next Claude session

1. **You are continuing an existing, working project.** Don't restart, restructure or rewrite. Before proposing anything,
   look for an existing implementation (search `apps/`, read the relevant ADR). Extend what exists.
2. **Read in this order:**
   1. `CLAUDE.md`
   2. this file
   3. `docs/ROADMAP.md`
   4. the newest `docs/PROGRESS.md` entries
   5. the ADRs relevant to the area you touch

   The repo outranks this document.
3. **Respect the non-negotiables in CLAUDE.md:**
   - camera and audio never leave the browser;
   - AI output is saved only after schema validation, and AI never changes the plan, timers or progress directly;
   - every query is scoped by `user_id`, with composite FKs and cross-user tests;
   - tests for deterministic code;
   - measured/estimated labels;
   - no secrets in git;
   - free-tier AI only, and no personal data in prompts;
   - COS330 is read-only and never in the repo; never process the owner's own submissions.
4. **AI work:**
   - Everything goes through `app/ai/` (`complete_text`/`complete_json`, roles in config).
   - Course text only through `app/ai/sources.py`.
   - Treat course text as untrusted.
   - Bound calls per unit of work.
   - Respect free-tier budgets and pacing, and never call a real provider in tests.
   - Run evals before and after prompt or model changes (once evals exist).
5. **User edits win.** The student's topics are anchors; reviewed, dismissed or unlinked items stay that way. Code, not
   the model, enforces this.
6. **Process:**
   - One roadmap task per branch (`phase-N/<task>`) and per PR.
   - `npm run check` must be green.
   - Tick ROADMAP and add a PROGRESS entry.
   - Write an ADR for real decisions; supersede ADRs rather than edit them.
   - Update ARCHITECTURE and PRODUCT in the same PR.
   - Run `npm run gen:api` after API schema changes.
   - Never edit a merged migration.
7. **Git safety:**
   - Never push to main, force-push, merge PRs, `reset --hard` or `git clean`.
   - Joshua merges.
   - Don't start `npm run dev` (Joshua runs it).
   - Ask Joshua to stop it before code changes, because the working tree is shared.
8. **Verify with evidence.** Don't claim tests pass or features work without running them or seeing the output. For AI
   features, check results on real COS330 data before calling the task done.
9. **Talking to Joshua:**
   - He wants a streamlined process: you make the technical decisions and give him exact commands and copy-paste
     prompts.
   - Ask only when a decision is genuinely his: scope, cost, privacy, or reversing an earlier decision.
   - Be explicit about assumptions.
   - Avoid over-engineering, and prefer working software.

---

## 11. Unknowns (could not be established from the repo)

- The PR number and CI result for `phase-2/topic-review` (probably #22).
- Whether migration 0014 is applied in Joshua's dev DB (probably not; the branch is unmerged).
- Whether COS330's last merge (17 Nov ~21:10) finished, or failed with "providers too busy".
- The material `kind` values in the dev DB (believed to be Slides, Past paper, Notes and Study guide after the
  re-upload; not re-checked).
- Whether `.wslconfig` has a memory cap.
- Exact free-tier quotas: Google doesn't publish them, and the budgets are estimates.
- The COS330 exam date (assessments can be added in the app).

---

## PROMPT FOR THE NEXT CLAUDE SESSION

Copy everything in the block below into a new Claude chat in the StudySensei Project:

```text
You're continuing development of StudySensei, an existing project: a personal study planner and tutor (React/Vite
web app + FastAPI/Postgres+pgvector API, free-tier Gemini/Groq AI). The repo is at C:\StudySensei on my Windows
laptop (GitHub: Josh-Heath123/StudySensei). I'm Joshua, the product owner and only user. My COS330 Computer Security
module is the real test data.

Your role: technical lead and reviewer. Claude Code (VS Code extension, Auto mode) does the implementation: you write
the task prompts I paste into it, review its reports and PRs, and check results yourself. I merge PRs and run
`npm run dev` in my own terminal. If you're Claude Code itself, follow CLAUDE.md's workflow directly.

Before doing anything else:
1. Read CLAUDE.md, then docs/PROJECT_HANDOVER.md (the full handover, written 17 Nov 2026). Use the device bridge or
   your file tools to read the repo directly.
2. Check the current git state (branch, last commits, uncommitted changes) and, where you can, PR/CI state
   (`gh pr list`, `gh pr checks`). Use read-only git with GIT_OPTIONAL_LOCKS=0 from the bridge.
3. Verify what the handover says against the code before relying on it. The repo, ROADMAP.md, PROGRESS.md and the
   ADRs in docs/decisions/ are the source of truth. If something has changed since the handover, say what.
4. Understand the architecture and the decisions behind it (ADRs 0001–0009) before proposing changes. Don't reverse
   an established decision without explaining why and asking me.

How to work:
- Continue from section 9 of the handover ("Immediate development handover"): first close out the topic review
  (PR on branch phase-2/topic-review → merge → migration 0014 → rebuild and review COS330's topic map → record the
  80 % check), then the next unchecked Phase 2 task (the pdf.js materials viewer), then the AI settings page and evals.
- Extend what exists. Don't restart, restructure or rewrite working code, and look for an existing implementation
  before proposing a new one.
- Respect the non-negotiables: user_id scoping with cross-user tests, schema-validated AI output, free-tier AI only,
  no personal data in prompts, COS330 read-only and never in the repo, no secrets in git, and one roadmap task per
  branch and PR.
- Give me exact commands and ready-to-paste Claude Code prompts. Tell me when to stop or start npm run dev (stop it
  while Claude Code edits; the working tree is shared).
- Don't claim anything works or passes without evidence. For AI features, check real COS330 results (built-in
  browser at http://localhost:5173, API via /api) before telling me to merge.
- Make the technical decisions yourself and state your assumptions. Ask me only when something is genuinely my call
  (scope, cost, privacy, or reversing an earlier decision).

Start by summarising, in a few lines, where the project stands after your checks, and what you want me to do next.
```
