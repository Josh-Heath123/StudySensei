# Roadmap

The single source of truth for status. Each `- [ ]` task is **one Claude Code session and one pull request**
(branch `phase-N/<task>`). Tick it in the same PR and add a `docs/PROGRESS.md` entry.

Phases follow dependencies first, then value. Every phase ends with software used in real study before the next starts.
Sizes: **S** is a handful of sessions, **M** about twice that, and **L** three to four times.

**Gates:** after Phases 1, 3, 6 and 9, review real use in the Project chat before continuing.

## Parallel spikes

- [ ] **S3 Visual direction** (alongside Phases 0–1, in the Project chat): three directions for Today, Session and Module → pick one → design system v1 input
- [ ] **S1 Camera in the browser** (alongside Phase 2): test background-tab throttling with a Web Worker + `MediaStreamTrackProcessor`, Document Picture-in-Picture, and a Tauri fallback. The result decides web vs Tauri for Phase 7
- [ ] **S2 Past-paper parsing accuracy** (alongside Phases 4–5): try segmentation and classification prompts on real COS330 papers and record the accuracy

---

## Phase 0: Reset and foundations (S)

**Objective:** a clean repository and a running skeleton.

- [x] Tag `v0-pyqt-prototype`, create branch `rebuild`, untrack `.venv/`, add `.gitattributes`, normalise line endings
- [x] Remove the legacy code and write `docs/legacy-notes.md`
- [x] `docker-compose.yml` (pgvector/pgvector:pg16, port 5433)
- [x] Scaffold `apps/api`: uv, FastAPI, `/health` with DB check, pydantic-settings, SQLAlchemy + Alembic, `users` migration, seeded local user
- [x] Scaffold `apps/web`: Vite, React, TS, Tailwind, shadcn/ui, router, sidebar shell (Today, Modules, Plan, Practice, Insights, Settings), connectivity status card
- [x] Root `package.json` (`npm run dev` / `check`), TypeScript client generated from OpenAPI
- [x] ruff, mypy, pytest, eslint, prettier, vitest and the GitHub Actions workflow
- [x] `CLAUDE.md`, `docs/PRODUCT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, decisions 0001–0002
- [x] Push `rebuild`, open the first PR (#1), and confirm CI passes on it
- [x] Stop hook (`scripts/stop-check.mjs`) runs `npm run check` when the tree has changes; narrow allowlist in `.claude/settings.json` (`uv run`, `npm run`, `git status/diff/log/add/commit`)

**Done when:**
- `npm run dev` opens the shell showing "API connected" and "Database connected"
- CI passes on a pull request
- the docs are committed

## Phase 1: Modules, assessments and study sessions (M)

**Objective:** a tool used every day, before any AI.
**Depends on:** Phase 0.

- [x] Models and migrations: `modules`, `topics` (tree), `assessments`, `assessment_topics`, `tasks`, with API tests for `user_id` scoping (data layer; each endpoint task adds HTTP-level cross-user tests)
- [x] Modules and topics REST endpoints and the Modules UI (create, edit, delete; code, name, colour, semester; manual topic tree)
- [x] Assessments and tasks endpoints and UI (date, weight, scope)
- [x] Today page: upcoming deadlines and empty states
- [x] `study_sessions` + `session_events` models and endpoints
- [x] `session-engine/timer.ts`: timestamp-based focus and break cycles, pause/resume, `localStorage` + server events. **Tests first:** pause and resume arithmetic, reload, sleep
- [x] Design system v1 (tokens, type scale, core components): `docs/DESIGN.md`, direction B "Planner" (done before the session screen so it's built in its final look)
- [x] Session screen: timer UI, breaks, end, 20-second reflection (focus 1–5, what was covered, confidence per topic)
- [x] Session history per module

**Verify:** timer unit tests, then a real 50-minute session with one reload and one break, where the timer matches the clock within 1 s.
**Done when:**
- three real study days are logged with no lost time
- session and timer tests pass in CI

## Phase 2: Materials and topic maps (L)

**Objective:** StudySensei understands a module from its files.
**Depends on:** Phase 1, a Gemini API key, and the COS330 files (read-only, never copied into the repo).

- [x] `Storage` interface (local folder in dev), `materials` model, upload endpoint (50 MB limit, type allow-list, SHA-256 dedupe)
- [x] `jobs` table and worker (`FOR UPDATE SKIP LOCKED`), added to `npm run dev`
- [x] Extractors: PDF (`pypdfium2`), PPTX, DOCX, plus a scanned-page flag, with fixture tests
- [ ] Chunker, `fastembed` (bge-small-en-v1.5, 384 dims), `tsvector`, hybrid search endpoint (RRF)
- [ ] `LLMClient` with **one OpenAI-compatible adapter** (Gemini primary, Groq fallback, optional Ollama; see decision 0002), `ai_usage` logging, budget and rate-limit backoff
- [ ] Topic-extraction prompts and Pydantic schemas (per material, then merged per module), with chunk–topic linking
- [ ] Upload UI with processing status, materials viewer (pdf.js, jump to page) and module search
- [ ] Topic review UI (confirm, rename, merge, delete; user edits win)
- [ ] AI provider settings page
- [ ] `evals/topic_extraction` and `evals/search` from COS330

**Verify:**
- extractor fixture tests
- 12 of 15 hand-written queries have the right slide in the top 3
- at least 80 % of proposed topics are kept with small edits

**Done when:**
- a module with at least 3 slide decks gets a topic map within about 3 minutes
- every AI call is in `ai_usage`

## Phase 3: Grounded tutor and voice v1 (M)

**Objective:** help during study, answered from your own material.
**Depends on:** Phase 2.

- [ ] Retrieval with a current-topic boost, and prompt templates (sources labelled as untrusted material)
- [ ] SSE tutor endpoint, plus `conversations` / `messages` storage with citations
- [ ] Tutor panel in the session: streamed answers, clickable [S1]–[S8] citations into the viewer, KaTeX
- [ ] "Explain differently", "Give an example", "Quiz me" (3 questions)
- [ ] `voice/stt.ts` (Web Speech API) and `voice/tts.ts` (`speechSynthesis`), push-to-talk, latency timing
- [ ] `evals/tutor`: 20 questions with expected source pages

**Verify:**
- at least 85 % of eval answers cite a correct page
- time to first token under 2 s
- speech starts within 2.5 s

**Done when:**
- the tutor is used in 3 real sessions and found useful
- results are in `evals/results/`

## Phase 4: Planner v1 (L)

**Objective:** decide what to study next and explain why.
**Depends on:** Phases 1 and 2.

- [ ] Availability models (`availability_rules`, `availability_exceptions`), workload and starting confidence per topic
- [ ] `services/planning/plan()` as a pure function. **Property tests first:**
  - no overlaps
  - stays within availability
  - respects the daily cap
  - two or more sessions per topic when time allows
  - a final review before each exam
- [ ] Feasibility report, plus the study-method rules table and the reason text for each block
- [ ] `plan_blocks` with `plan_version`, and re-planning triggers (skip, finish, new assessment or material, nightly)
- [ ] Week view (drag to move, mark days unavailable), and the next block on Today with its reason
- [ ] Web Push (VAPID, `pywebpush` from the worker) and a private ICS feed

**Verify:** a scenario with 2 modules, exams in 10 and 20 days and 12 h/week available. Skip a block and check the plan adjusts and explains why.
**Done when:**
- the plan is followed for a week with at most one manual change a day
- the property tests pass

## Phase 5: Practice and mastery (M)

**Objective:** measure understanding and build it.
**Depends on:** Phases 2 and 4.

- [ ] `practice_items` + `reviews`, and the generation job (flashcards and questions linked to source chunks)
- [ ] FSRS integration (`py-fsrs` / `ts-fsrs`) and the review queue
- [ ] Mastery formula with unit tests, documented in `services/mastery/README.md`
- [ ] Practice UI: own cards, short-answer AI marking against a reference, self-marking
- [ ] Connect mastery to "Quiz me" and planner priority

**Verify:**
- 30 generated questions are spot-checked, and at least 90 % can be answered from their source
- due dates follow FSRS

**Done when:**
- the review queue has worked for a week
- the plan shifts toward weak topics

## Phase 6: Past-paper intelligence (L)

**Objective:** learn how each module is actually assessed.
**Depends on:** Phases 2, 4, 5 and S2.

- [ ] `past_questions` + `past_question_topics` models, and past-paper upload with year and sitting
- [ ] Opt-in transcription of scanned pages with a vision LLM (shows page count first)
- [ ] Segmentation and classification prompts and schemas (from S2), plus a correction UI
- [ ] Assessment-profile queries (exact counts) and a profile page with drill-down; hidden below 3 papers
- [ ] Past questions in practice, timed paper mode, and profile weights feeding planner priority and tutor emphasis
- [ ] `evals/pastpapers` from hand-labelled COS330 papers (excluding the student's own `u23541475_*` submissions)

**Verify:**
- at least 90 % of questions segmented correctly
- at least 80 % agreement on topic mappings
- profile numbers match a hand count

**Done when:** with 3 or more papers the profile is shown; with fewer, only the evidence is shown, with a notice.

## Phase 7: Camera companion, opt-in (L)

**Objective:** supportive, private nudges that are rare and correct.
**Depends on:** Phase 1 and S1.

- [ ] Vision worker (built from S1's approach), consent flow, camera indicator and pause button
- [ ] Landmark-trace recorder (numbers only) for test fixtures
- [ ] `vision/signals.ts` (presence, head yaw and pitch, blink edges with hysteresis, posture deviation). **Fixture tests first**
- [ ] 5-second calibration and per-minute summaries (`session_minutes`)
- [ ] `session-engine/interventions.ts`:
  - posture nudge after 3 min of drift, at most once every 15 min, never in the first 10 min
  - away for more than 5 min pauses the timer
  - quiet mode
- [ ] Screen and Desk/paper modes, the companion mini-window, and a performance governor

**Verify:**
- upright, slumped and leaning are told apart in fixtures
- blink counts within ±20 %
- acceptable CPU use
- at most 4 nudges per hour

**Done when:** after 5 real camera sessions, you choose to keep it on.

## Phase 8: Profile and insights (M)

**Objective:** get measurably better at knowing you each week.
**Depends on:** Phases 1, 4 and 5 (and 7 for camera items).

- [ ] Metric jobs for `profile_metrics` (value, sample size, measured or estimated), with tests on synthetic histories
- [ ] Recommendation rules and `recommendations` with their evidence
- [ ] Insights page and weekly review (no insight before its threshold)
- [ ] AI write-ups of the computed statistics (never inventing numbers)
- [ ] Revisit the legacy phase and pattern heuristics against real data (`docs/legacy-notes.md` §5)

**Done when:** after 3–4 weeks, at least 3 recommendations strike you as accurate.

## Phase 9: Beta readiness (M)

**Objective:** safe and affordable for other students.

- [ ] Supabase Auth, and cross-user access tests for every endpoint
- [ ] Hosting: API and worker image on Fly.io/Railway/Hetzner, Supabase Postgres + Storage, web on Cloudflare Pages
- [ ] Onboarding with course-outline import
- [ ] Privacy centre (export and delete everything) and the retention jobs
- [ ] Per-user AI budgets and bring-your-own-key (encrypted)
- [ ] Error monitoring, backups and a restore drill
- [ ] POPIA review

**Done when:** classmates use it for 2 weeks with no data or privacy incidents.

## Later

- [ ] MCP connector (read-only: `get_modules`, `get_plan`, `get_weak_topics`, `search_materials`)
- [ ] Google and Outlook calendar sync
- [ ] Mobile polish (reviews on your phone)
- [ ] Better voices or real-time voice
- [ ] Tauri wrapper, if S1 calls for one
- [ ] Shared class modules (after a copyright and privacy review)
