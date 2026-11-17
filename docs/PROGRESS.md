# Progress log

Newest first. 3–5 lines per session: what was done, what was decided, what's next.

## 2026-11-17: Phase 2, the materials viewer

- **Done:**
  - `GET /materials/{id}/file` streams the original: inline with its filename, nosniff, the sha256 as an immutable
    ETag, and 304 for a matching `If-None-Match`.
  - `MaterialViewer` draws PDFs with pdf.js. Each document is opened once, fitted to the width, sharp at the device
    pixel ratio, and a drawing in flight is cancelled when the page changes. Other kinds show their text.
  - Navigation: previous and next, a page box, ←/→ and "Page N of M". A PDF that fails falls back to its text.
  - It sits in `PagesDialog`, which every entry point opens at the right page. The row button is now "View".
- **Bundle:** pdf.js is lazy, a 444 kB chunk (134 kB gzipped) plus a 1.27 MB worker, loaded on first view. The
  main bundle grew 7 kB, from the viewer code.
- **Tests:** API (bytes, headers, 304, missing blob, cross-user), Vitest (navigation, cancel, fallbacks) and
  Playwright (a search result opens the PDF at its page; the canvas draws; jumping works).
- **Next:** the AI provider settings page.

## 2026-11-17: Phase 2, merge size fix and a stale topic-map error (decision 0010)

- **Found:**
  - COS330's compact merge request is 27,216 characters with no descriptions, and Groq counts it as 9,072 tokens (it
    refused it with a 413: "Limit 8000, Requested 9072"). Gemini counted 9,031.
  - That's about 3.0 characters a token, not the 3.5 ADR 0009 assumed.
  - The proposal names alone are 13,336 characters. The JSON instruction, system prompt, header and existing topics
    add another 6,803.
- **Done:**
  - The merge's own ratio is now 2.5 (`MERGE_CHARS_PER_TOKEN`), so the budget is 17,500 characters. It was the only
    user of the ratio; extraction is capped in characters.
  - A request over budget with no descriptions logs a warning with the numbers. Topics are never dropped.
  - A COS330-sized test is a strict xfail until the input fits.
  - The topic-map status now reports only failures newer than the latest successful merge.
- **Not fixed:** COS330's merge still can't fit Groq. Gemini takes it, as before.
- **Next:** decide how to make the merge fit, if Groq should be able to take it. That needs a shorter format or a merge
  in halves.

## 2026-11-17: Phase 2, topic review (decision 0009)

- **Merge fallback:**
  - The merge input is now compact: ids, names and page counts, plus descriptions only while the request stays
    under 7,000 estimated tokens. COS330 goes from 68.7K to 24.8K characters, so Groq can take it.
  - A 413 moves on like a 429 (`too_large`) without using the call cap or cooling the model down.
- **Review:**
  - Each AI topic has Keep, Rename, Merge into (subtopics, cited pages and page links move to the target) and
    Dismiss (deleted and remembered; the merge never adds the name again). A dismissed topic can be restored.
  - A Review filter with "N of M reviewed" and "Keep all remaining".
  - Outcomes recorded in `topic_reviews` and shown on the tab and in the topic-map status.
- **Linked pages:** clicking a topic lists its pages by material (cited, or similar with the score), each opening
  the page text. Unlink is remembered across relinking (`topic_unlinks`).
- **Decided:**
  - The AI's old name of a renamed or merged topic adds to the topic that carries it now, rather than a duplicate.
  - Dismissing a topic takes its unreviewed AI subtopics with it; the student's own subtopics move up.
- **Next:** start the dev servers (migration 0014), rebuild COS330's map, review it, and read the 80 % check off the
  review line. Then the AI provider settings page.

## 2026-11-17: Phase 2, the three COS330 materials that still failed

- **Found** (from `ai_usage.detail`): the Chapter 1, 5 and 7 notes made 12 calls in all, and none was a content
  refusal.
  - 9 were Gemini 503 "high demand". Each counted toward the 4-call cap and was retried on the same model, then the
    job waited and repeated, so Chapter 7 used its 4 calls on 503s alone.
  - 2 replies (Chapters 1 and 5) had no `name` on any topic or subtopic, so the model used another key. They never got
    a working repair because the repair hit a 503.
  - 1 was Groq's 413 (Chapter 5 was 13.4K tokens against an 8K tokens-a-minute limit), which moved on correctly.
- **Done:**
  - A 503 now moves on to the next model like a 429 (`overloaded`).
  - 429s and 503s no longer use the per-material cap; they have their own cap of 20.
  - A content refusal or empty reply moves on without spending the repair (`refused`), and `AIRefused` fires when
    every model declines.
  - A topic's name is also read from `title`, `topic`, `heading` or `label`.
  - A nameless reply records its keys in `detail`.
  - Migration 0013. ADR 0008.
- **Next:** merge, run migration 0013 (start the dev servers), then Retry topics on the three materials.

## 2026-11-18: Phase 2, topic map fixes after the first COS330 run

- **Found:** 21 materials took 142 extraction calls and 13 merge calls, where ~22 were needed.
  - **Flash-Lite:** 66 replies were `invalid_json`, and 28 calls failed with HTTP errors.
  - **3.8 Flash:** all 18 of its daily budget went (8 timeouts at 90 s).
  - **Groq:** 10 errors, probably requests too large for its tokens-per-minute limit.
  - **Failed materials:** 3, the Chapter 1, 5 and 7 notes.
  - **Cause:** errors cascaded through every fallback, and rescheduled jobs repeated the whole cascade. No failure
    reasons were stored. Details are in ADR 0007.
- **Done:**
  - **Diagnosis and output:** `ai_usage.job_id`, `detail` and a `truncated` outcome (0012); lenient topic schemas;
    `finish_reason` checks.
  - **Bounded runs:** parts of about 40 pages, combined; cut-off parts split; finished parts saved for retries; at most
    4 calls and 1 repair per material per run.
  - **Client:** only 429, timeouts, lost connections and 413 move on to another model; a persistent 5xx waits; other
    refusals fail. Per-model requests-per-minute pacing.
  - **Merge prompt:** keeps the module's naming style and one top-level topic per chapter deck.
  - **UI:** per-material topic state with "Retry topics" on the Materials tab; "Clear AI topics" on the Topics tab.
  - **Tests:** 42 new API tests and 4 new web tests.
- **Decided:** 429s don't count toward the daily budget, but do count toward the per-run cap (ADR 0007).
- **Next:** rebuild COS330 (Clear AI topics, then Build topic map) and check `ai_usage`: about one call per material.
  Then Phase 2 task 7.

## 2026-11-17: Phase 2, task 6 (AI topic maps)

- **Done:**
  - **`extract_topics`** per eligible material, queued after indexing and backfilled by migration 0011. Prompt with
    labelled pages and scanned figures; `MaterialTopics` schema; stored in `topic_proposals` with the model that answered.
  - **`merge_topics`** with existing topics as fixed anchors. Code applies only additions (`source = ai`) and cited
    pages (`topic_pages`). Any edit, including a move, makes a topic the student's.
  - **`chunk_topics`** by cited pages and by local similarity (threshold 0.63, calibrated on synthetic fixtures with
    bge-small and pinned by a real-model test). `link_topics` rebuilds it when topics change.
  - **API and UI:** a new `long` AI role (Flash-Lite → 3.8 Flash → gpt-oss-120b). `GET /modules/{id}/topic-map` and
    `POST …/build`, plus `linked_pages` in the tree. The Topics tab has an AI badge, page counts, and a build panel
    with progress and honest states.
  - **Tests:** 32 new API tests and 12 new web tests, covering the prompt, schema, repair, allow_ai, anchoring,
    re-runs, source switching, both link methods, the backfill and cross-user cases.
- **Decided:** ADR 0006.
  - "Build topic map" analyses only materials without a proposal (no quota spent on repeats).
  - A topic the student deletes can come back on the next merge; the review task should add a dismissed list.
- **Next:** Phase 2 task 7, the upload UI with processing status, the materials viewer and module search. Before
  that, try a real topic map on COS330 with both keys.

## 2026-11-17: Phase 2, AI routes rebalanced, vision role

- **Why:** pings showed `gemini-3.8-flash` timing out at 30 s (default and `low`) on a ~20-a-day free tier, while
  `gemini-3.5-flash-lite` answers in 1–10 s on ~500 a day.
- **Done:**
  - **smart:** Groq `gpt-oss-120b` → Flash-Lite → 3.8 Flash (last resort), all `low`
  - **bulk:** Flash-Lite (`minimal`) → `gpt-oss-20b` (`low`)
  - **New `vision` role:** Flash-Lite → Groq Qwen → 3.8 Flash. Any request with an image goes there and is logged as
    `vision` (migration 0010). It replaces `AI_VISION_MODELS`, and every model in it was checked in the provider docs
    for image input.
  - ADR 0002 has a second dated update, ARCHITECTURE has the new routes and the reasons, and there are new tests for
    vision routing and fallback.
- **Decided:** budgets are unchanged (no new published numbers). Ollama stays out of `vision`.
- **Next:** rerun the ping with both keys, then Phase 2 task 6 (topic extraction), which will mostly run on gpt-oss-120b.

## 2026-11-17: Phase 2, LLM client fix (supported thinking levels, provider error text)

- **Why:** the ping got HTTP 400 from `gemini-3.8-flash` in 0.4 s. It doesn't support `minimal`, which the ping sent to every model.
- **Done:**
  - `AI_REASONING_EFFORTS` lists the levels each routed model accepts, from Gemini's thinking docs and Groq's reasoning docs
    - 3.8 Flash: low/medium/high
    - Flash-Lite: all four
    - gpt-oss and Qwen: low/medium/high
  - `wire_effort` raises a missing level to the model's lowest supported one, replacing the Groq-only special case. Qwen now gets a level too.
  - `ProviderError` carries the provider's `error.message`, trimmed to 300 characters
  - tests:
    - the effort table now runs per model from config (8 cases)
    - level raising, and every routed model having its levels listed
    - the ping sending low to Flash and minimal to Flash-Lite
    - a 400 body's message appearing in the error, trimmed, with nothing from the headers
- **Next:** rerun `uv run python -m app.ai.ping`, then Phase 2 task 6 (topic extraction).

## 2026-11-17: Phase 2, LLM client follow-up (thinking level, timeouts, ping output)

- **Why:** the ping hung on `gemini-3.8-flash` with no output. Gemini 3 always thinks at its default level unless told
  otherwise, and the old single 90 s timeout gave no feedback while it waited.
- **Done:**
  - each route in config has a `reasoning_effort` (bulk `minimal`, smart `low`), sent only to Gemini and Groq's gpt-oss
    (`minimal` is sent as `low`, its lowest); a call can override it
  - a 10 s connect timeout and a separate 90 s read timeout; a timeout is retryable, logged as `timeout` (migration
    0009) and counts against the budget
  - the ping prints `→ provider/model …` first, flushed, and then `ok`/`FAIL`. It uses `minimal` and gives each model
    30 s in total, then moves on
  - 16 new tests on the fake transport, including a slow fake that trips the ping limit while the next model still answers
- **Next:** run `uv run python -m app.ai.ping` with real keys, then Phase 2 task 6 (topic extraction).

## 2026-11-17: Phase 2, task 5 (LLM client)

- **Done:**
  - `app/ai/`: one OpenAI-compatible adapter (httpx) for Gemini, Groq and optional Ollama; `LLMClient.complete_text` / `complete_json` (Pydantic validation, one repair turn); image messages, sent only to vision models.
  - Routing: roles `smart` / `bulk` are ordered `provider/model` lists in config. A model is skipped when it has no key or is cooling down, and when it's out of budget (counted from `ai_usage` since the provider's midnight). 429/5xx honour Retry-After (or back off with jitter), retry once if ≤ 20 s, then fall through. When all are out, `AIUnavailable(retry_at)`: the worker reschedules the job without using an attempt; the API gives 503 + Retry-After.
  - `ai_usage` (migration 0008), one row per request, no prompt or reply text. `GET /ai/status` (keys yes/no only, roles, today's usage vs budget). `uv run python -m app.ai.ping`.
  - Privacy gate `app/ai/sources.py`: chunks and pages for prompts are filtered on `allow_ai` in the query, and file names are never sent. Tested end to end against what the fake provider received.
  - Tests: 42 new tests (`FakeLLM` transport). `conftest` blanks real keys and installs a client that refuses any request, so the Stop hook and CI never reach a provider.
- **Decided:**
  - Models: smart = `gemini-3.8-flash` → `openai/gpt-oss-120b` → `qwen/qwen3.8-27b`; bulk = `gemini-3.5-flash-lite` → `openai/gpt-oss-20b`. Budgets 18/450/900/900/900 per day (free tier less ~10 %). Recorded in an addendum to ADR 0002.
  - Google no longer publishes free-tier limits. Flash at 20 RPD is the binding constraint, so Groq will carry much of the smart load.
  - Budgets count per user (keys become per-user in Phase 9); a 429 doesn't count against quota.
- **Next:** Phase 2 task 6, topic-extraction prompts and schemas. Run `uv run python -m app.ai.ping` with real keys first.

## 2026-11-14: Phase 2, task 4 (chunking, local embeddings, hybrid search)

- **Done:**
  - Chunker (`services/search/chunking.py`, pure): one page at a time, at most 400 tokens by the model's own tokenizer, split at paragraphs → lines → sentences → words as needed, ~50 tokens of overlap; chunk text is a slice of the page.
  - `chunks` (migration 0007): page number, position, text, token count, `vector(384)`, generated english `tsvector` + GIN; composite FKs to the material (user and module) and to its page, so re-extraction and deletes cascade.
  - Pipeline: `extract_text` queues `index_material`; a material is "Ready" only once indexed ("Indexing for search…" until then). The migration re-queues materials already extracted.
  - fastembed `BAAI/bge-small-en-v1.5` (`passage_embed` / `query_embed`, batches of 32), loaded once per process, cached in `data/models` with a clear log on the first download.
  - `GET /modules/{id}/search?q=&limit=8`: exact cosine top 20 + `websearch_to_tsquery`/`ts_rank_cd` top 20, RRF (k = 60), `ts_headline` snippets as plain/highlighted parts. HTTP cross-user case added.
  - Web: a search box at the top of the Materials tab; results show the snippet, file name and page, and open the page-text view at that page. Honest states while nothing is indexed, while files are still processing, and for ready files with no text layer.
  - Tests: API 375 (a deterministic fake embedder; one smoke test with the real model on the fixtures), web 255, e2e 2 (the upload test now searches and opens the result). CI caches `data/models`.
  - ADR 0005; ARCHITECTURE's "400–800 tokens" corrected to 400 (the model truncates at 512).
- **Decided:**
  - no vector index yet: an exact scan filtered by user and module never misses and is fast at this size (ADR 0005 says when HNSW is worth it)
  - lines are a split level between paragraphs and sentences, because slide bullets rarely end in full stops
  - the embedded text leads with "material · page title"; stored text and the keyword index don't
  - local embedding ignores `allow_ai`; that switch is for text sent to Gemini
- **Next:** Phase 2 task 5: the `LLMClient` with one OpenAI-compatible adapter, `ai_usage` logging, budget and backoff.

## 2026-11-13: Phase 2, task 3 (text extraction)

- **Done:**
  - `extract_text` replaces `count_pages`. Pages go into `material_pages` (migration 0006: page number, title, text, char count, is_scanned), and `scanned_page_count` is stored on the material.
  - Readers:
    - PDF (pypdfium2)
    - PPTX (python-pptx): title, body and tables, then speaker notes; one page per slide
    - DOCX (python-docx): split at headings or ~800 words, tables included
    - MD (split at `#` headings), TXT (~800 words)
    - images: one empty, scanned page
  - Scanned means fewer than 20 non-space characters.
  - Damaged and password-protected files fail at once, with a readable reason (new `JobError(retry=False)`).
  - The migration queues extraction for every material uploaded before it, renaming waiting `count_pages` jobs instead of duplicating them.
  - API: `GET /materials/{id}/pages` and `/pages/{n}`, with cross-user cases.
  - Web: "Ready · 4 of 12 pages scanned"; pages and scanned pages in the details; "View text" opens a plain page-by-page viewer.
  - Fixtures: small generated files in `apps/api/tests/fixtures` (`make_fixtures.py`, using pikepdf as a dev dependency for the encrypted PDF): a 3-page PDF with an image-only page, a password-protected PDF, a 3-slide PPTX with notes and a picture-only slide, and a DOCX with headings, a table and a long section.
  - Tests: API 322, web 251, e2e 2 (the upload test now reads the extracted text in the viewer).
- **Decided:**
  - one row per page, replaced on re-extraction
  - speaker notes are part of the slide's text, after a "Speaker notes:" label
  - the 20-character threshold counts non-whitespace characters, including notes
  - retries are for transient errors only; a file that can't be read fails immediately
- **Next:** Phase 2 task 4: the chunker (reading `material_pages`), fastembed embeddings, `tsvector` and hybrid search.

## 2026-11-13: Phase 2, tasks 1–2 (material uploads, storage, job worker)

- **Done:**
  - **API:**
    - a `Storage` interface with `LocalStorage` (`data/materials`, atomic writes, keys `{user_id}/{sha256}` validated against path escapes)
    - `materials` and `jobs` (migration 0005)
    - upload: 50 MB (413), an allow-list checked by content (415), and the same file twice in a module is a 409 naming the original. Files are shared across a user's modules and deleted with the last material that uses them, module deletes included.
    - list, get, PATCH (title, kind, allow_ai), delete and retry
  - **Jobs:**
    - `claim_next` with `FOR UPDATE SKIP LOCKED`, which also takes back stale locks after 10 minutes
    - retries after 30 s, 2 min and 8 min, then failed; readable reasons on the material while it retries
    - `count_pages` (pypdfium2 for PDF, PPTX slides, DOCX `<Pages>`, images 1, text none) marks the material ready
    - the worker runs in `npm run dev`
  - **Web:** a Materials tab on the module page:
    - drag-and-drop or Choose files, checked locally
    - each file staged with a guessed kind, a title and "Allow AI processing", uploaded one by one with its own result
    - a live list (polls every 2 s while anything is in flight) with status, the AI switch, Retry and Delete
  - **Tests:**
    - API 308 (storage, file types, upload validation and dedupe, the job lifecycle including a retried failure, a stale lock, SKIP LOCKED on two connections, page counts, cross-user)
    - web 246
    - e2e 2: a real-browser upload processed by the real worker, plus the duplicate message
  - ADR 0004
- **Decided:**
  - blobs are per user (never shared across accounts) and keyed by hash
  - duplicates within a module are refused; across modules they share the blob
  - the type is checked by content, not trusted from the name
  - jobs carry `user_id`, and handlers scope by it
  - `allow_ai` defaults on and is switched off by hand; nothing is guessed from filenames
  - e2e runs use their own storage folder (`data/e2e-materials`, cleared each run) and start the real worker themselves
- **Known gaps:**
  - Starlette spools a multipart upload before the endpoint sees it; the 50 MB check happens from `Content-Length` and while hashing, not at the socket
  - a blob delete racing an upload of the same file is possible but unlikely (ADR 0004)
- **Next:** Phase 2 task 3: extractors (PDF with pypdfium2, PPTX, DOCX) and the scanned-page flag, as jobs that replace `count_pages`.

## 2026-11-13: Phase 1, task 8 (session history per module)

- **Done:**
  - API:
    - `GET /modules/{id}/sessions` is now paginated (`limit`/`offset`, a page with `total`), with the open session first, then newest first
    - new `GET /modules/{id}/sessions/summary?week_start=` for counts and active time, all time and this week
    - HTTP cross-user cases for both
  - web: a Sessions tab on each module page:
    - a Measured summary (this week, all time, session count)
    - sessions with date, topic, active and break time, focus and confidence per topic; the open one is at the top with Resume
    - "Show older sessions" loads 20 at a time
    - a detail dialog with the reflection and the event timeline
  - `mockApi` handlers receive the query string
  - tests: API 239, web 223, e2e 1
- **Decided:**
  - pagination is offset-based: history is small and append-mostly, and offsets keep "Show older" simple
  - "this week" is the student's local week, Monday 00:00, sent by the client; a session counts in the week it started
  - study time means active time; breaks are shown but never counted as study
- **Next:** Phase 1 verify (a real 50-minute session with a reload and a break), then the Phase 1 gate: three real study days.

## 2026-11-13: Phase 1, task 7 (session screen)

- **Done:**
  - `/session` (focus mode, no top nav):
    - the header (← Today, module badge, topic, End session) and the 6 px progress line
    - eyebrow, 128 px numerals, the segmented focus/break bar, Pause/Resume, Break now/End break
    - honest Materials (Phase 2) and Tutor (Phase 3) placeholders
  - remaining time in `document.title`
  - Start session on Today (next-up card) and on each module page, with a module and optional topic. It becomes "Return to session" while one is open, and a reload lands back in it.
  - break due, offline and refused-event notices are in-page banners; the away question is the only dialog
  - the reflection (focus 1–5, what I covered, confidence 1–5 per ticked topic) is saved via `PUT /sessions/{id}/reflection`, then a summary (Measured, with the event count) links back to Today
  - `controller.ts` + `display.ts` (pure, tests first); the engine snapshot gains `eventCount` and keeps the server id after an ended session syncs
  - tests:
    - web 212: display, controller, and a fake-clock flow covering start → pause → resume → break → end → reflect, plus reload, away, online and visible flushes, and the 30 s retry
    - one Playwright test (`npm run e2e`) against the real API, with a reload mid-session
  - new CI job `e2e`
- **Decided:**
  - Playwright runs on its own ports and database (:8001 / :5174 / `studysensei_e2e`) and stays out of `npm run check`, to keep the Stop hook fast
  - the browser clock is paused three hours back so times are exact and never in the server's future
  - an ended session waits in localStorage for its reflection, with a Skip, so a forgotten reflection never blocks the next session
- **Known gap:** reloading while offline after the start was synced restores nothing until the API answers, because the engine only restores offline from a queued start.
- **Next:** Phase 1 verify: a real 50-minute session with one reload and one break. Then Phase 1 task 8, session history per module.

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
