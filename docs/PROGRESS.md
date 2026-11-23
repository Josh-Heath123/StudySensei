# Progress log

Newest first. 3–5 lines per session: what was done, what was decided, what's next.

## 2026-11-23: Phase 5, task 3 (topic mastery v1)

- **From #49's review:** listed reviews carry `desired_retention` and `after {state, due}`; queue counts add
  `new_allowance_left` beside `new_today_left` (capped by the new items there are).
- **Mastery (ADR 0027):** pure `services/mastery/formula.py` with its constants in one module; recall (FSRS R),
  recency-weighted accuracy (first review per local day, Quiz me answers) and the rating. Properties first: the
  monotonicity one failed first on the task's `w·E + (1 − w)·P` (a wrong quiz answer raised it), so recall now carries
  its share by its own sample. Worked examples: 25 % (new, rated 2), 91 % (ten Good cards), 78 % (30 days on).
- **On read, nothing stored:** `GET /modules/{id}/mastery`, `GET /topics/{id}/mastery` with cross-user cases; 60 topics
  and 600 items in about 33 ms. The topic dialog shows the band and its basis under Starting confidence.
- **Next:** task 4, the practice UI.

## 2026-11-22: Phase 5, task 2 (FSRS scheduling and the review queue)

- **From #48's review:** the spot check is committed (`evals/results/practice-cos330.json`): 47 of 48 answerable,
  97.9 % against 90 %, so **Phase 5's first Verify line is met**. The generation prompt now forbids invented reasons,
  examples and facts; items list distinct cited pages. The two dry runs again kept 8 of 8 each.
- **FSRS (ADR 0026):** `fsrs` 6.3.3 pinned, fuzzing off; pure `schedule`/`replay` with a golden test against py-fsrs
  (due dates follow FSRS) and Hypothesis properties (none failed, even at 4,000 examples).
- **Data (0026):** `practice_item_states`; review snapshots, retention and library version; `practice_new_per_day` and
  `practice_desired_retention` on users. Reviews run under a row lock (a concurrent pair is serialised); a suspended or
  rejected item is a 409. Previews per grade, the queue (due, then new within a local-day allowance, DST-tested) and
  settings. Simulation: about 130 reviews (45 active minutes) a day by day 30 at the defaults.
- **Next:** task 3, the mastery formula.

## 2026-11-21: Phase 5, task 1 (practice items, reviews and the generation job)

- **Review fixes from #47:** a done block's calendar event says "Done · 48 min studied (measured)."; a push TTL is
  worked out when sending and a reminder for a started block is dropped; "COS330 X was deleted."; done grid cards are at
  least 24 px; the worker prunes `reminders_sent` over 30 days; ROADMAP Phase 9 gains push-host and calendar rate limits.
- **Data (0025, ADR 0025):** `practice_items`, `practice_item_sources`, `practice_generations`, append-only `reviews`
  (a trigger refuses UPDATE); one prompt per topic unless rejected; one queued or running generation per topic.
- **Generation:** the topic subtree's AI-allowed learning material (never past papers, tests, assignments or outlines),
  best link first within 4,500 tokens; a pure filter with counts by reason; a `generate_practice` job that waits out
  rate limits. Endpoints with cross-user cases; topic merges move items. Dry runs on a chapter and a subtopic: 8 of 8
  kept each. Eval: 48 requested, 48 kept (one earlier run had one topic fail validation twice; it didn't recur).
- **Next:** the reviewer marks the spot-check sheet (`evals.practice score cos330`); then task 2, FSRS and the queue.

## 2026-11-22: Phase 4, task 6 (Web Push reminders and the private ICS feed)

- **Review fixes from #46 (ADR 0023), tests first:** a done block shows at its session's measured time (it hid under
  the block that re-used its slot) with `planned_start`/`planned_end`; drags drop from the pointerup, heard on the
  window (a flick was lost); no day menu on past days and the agenda starts at today; card names with day and state;
  sticky day headers; Move… on the block's own time; a version when an assessment's blocks cascade away.
- **One clock:** `clock.now()` with `FAKE_NOW` (demo and e2e databases only). The screenshots run the API, worker and
  browser at Thu 19 Nov 18:20, with three days of seeded history, so QA finally showed planned, Now, done, skipped and
  missed together; it found a clipped first hour label and "(measured)" cut on done grid cards.
- **Reminders (0024, ADR 0024):** `push_subscriptions`, `reminders_sent` (one per slot, not per block id),
  `calendar_feeds` (hashed token), `users.reminder_minutes`; pywebpush behind `PushSender`; the worker queues reminders
  once a minute; Settings → Reminders and Calendar; a push-only service worker. e2e fetches the .ics.
- **Next:** a week of real use for Phase 4's "done when", then Phase 5.

## 2026-11-21: Phase 4, task 5 (the week view, moving blocks, and Next up from the plan)

- **Review fixes from #45 (ADR 0022), tests first:** a linked session follows its block into a new version (it used to
  mark the superseded row done); only a planned block is marked done; no skip with an open session; a true skip
  summary ("no free time left … now 4 h 10 short"); version 1 is "Your first plan."; no nightly retry loop.
- **Moves:** `plan_blocks.pinned` (0023), six pure rules with sentences, `POST /plan/blocks/{id}/move`, pinned blocks
  carried past 24 h while valid. The accepted-move property failed first on the final review's window, so a sixth
  rule (`review_window`) keeps a review in its last 3 days.
- **`GET /plan`:** history, derived missed status (no write), linked session and measured minutes, server actions,
  `replan_pending`. Sessions start for a block; a refused block is dropped once offline so the session is kept.
- **Web:** `/plan` (grid with drag, agenda, popover or sheet, Move…, day menu, polling) and Today's Next up and Your day
  from the plan. QA screenshots at 1440/768/375 in both themes found clipped card titles, wrapping times, faint free
  bands and a sideways scroll on Today at 375 px; all fixed. e2e drags, refuses, skips and finishes a planned block.
- **Next:** task 6, Web Push and the ICS feed.

## 2026-11-21: Phase 4, task 4 (plan versions, blocks and re-planning)

- **Review fixes from #44 (ADR 0020):** pass 3 spreads a single unit (2, 2, 1, 1 over four evenings, was 3, 1, 1, 1);
  the overall line says "Nothing more is needed…" or names the short assessment when the time is there; "under 1 min
  studied"; topic estimates in the planner's format everywhere ("≈ 2 h 15"); the 7 h example.
- **Data (0022, ADR 0021):** `plan_versions`, `plan_blocks` (composite FKs on `user_id`), the session's block FK and
  one queued re-plan per user. Nothing is pruned.
- **Planner:** fixed blocks (busy, under the cap, counted for their unit and review) and today's measured minutes
  against today's cap. Properties first; the review property failed first (its "room" didn't count fixed blocks).
- **`replan()`:** advisory lock, missed blocks, the next 24 h fixed, skipped slots kept free (the first scenario run
  put the skipped block straight back), one code path with the preview, no churn. Triggers coalesce through
  `enqueue_replan`; nightly after local 03:00.
- **API:** `GET /plan`, `GET /plan/next`, skip, replan; `POST /sessions` with `plan_block_id`. Demo: version 1, then a
  skip that moves the block to 18:50 with "You skipped TCP congestion control (Fri 20 Nov, 18:00): …".
- **Next:** task 5, the week view and the next block on Today with its reason.

## 2026-11-20: Phase 4, planning scope (a fix PR from the review of #43; ADR 0019)

- **Subtrees:** an assessment that ticks a topic covers its subtree. Each ticked topic with no ticked ancestor is one
  planning unit, with its workload over the subtree's distinct pages, its sessions and the subtopics' mean
  confidence when it isn't rated itself (`services/planning/subtree.py`). On the real COS330 tree (counted read-only),
  Ch5 with its 5 subtopics drops from 9 h 50 (12 minimum blocks) to 4 h 15 (2); Ch1 alone rises from 2 h 15 to 4 h 20.
- **UI:** the topic tree's `workload_with_subtopics` (same code) shows in a chapter's dialog; the assessment form
  shows a ticked topic's subtopics as "Included with …" (only what's ticked is saved).
- **Course order** breaks priority ties (pre-order in the tree): four unrated chapters start Ch1, Ch2, Ch3, Ch4 with
  no change to the passes. **Final reviews** only for exams, tests and quizzes; an assessment whose topics are planned
  for a sooner one says so.
- **Demo run:** the synthetic chapters estimate 25 min each across their subtopics, and the week of sessions on those
  subtopics now counts for them, so only Semester test 2's review is planned and Assignment 3 gets no review.
- **Next:** task 4, `plan_blocks` with `plan_version` and the re-planning triggers.

## 2026-11-20: Phase 4, task 3 (feasibility report, study methods and reason text)

- **Fixes from the review of #42:** docs/README lists decisions 0001–0018; the evals README intro names the tutor eval.
- **Inputs from the database** (`services/planning/inputs.py`): free time for 1–62 local days, upcoming assessments
  due in the window (later ones are listed, not planned), workload and confidence, and measured minutes per topic
  (a subtopic's sessions count for it only). Tests: another user's rows never count, a past assessment is left out,
  an exception empties its day.
- **Methods, text and feasibility** (ADR 0018, all pure): a four-row method table; one or two code-written sentences
  per block, every minute labelled estimated, yours or measured; per-topic, per-assessment and overall required,
  planned, short, free and booked minutes with fits/tight/short and levers. Hypothesis checks planned + short =
  required, the sums and the status (about 11 % of examples tight, 35 % short).
- **Preview:** `GET /plan/preview?days=` (cross-user case) and `python -m app.planning.preview`. The dev DB has no
  assessments or study time yet, so the CLI ran on the demo seed, which now has weekly study time. It showed that
  a parent topic whose pages are linked to its subtopics gets a tiny estimate (5 min) and two default-length blocks.
- **Next:** task 4, `plan_blocks` with `plan_version` and the re-planning triggers.

## 2026-11-20: Phase 4, task 2 (the pure planner, property tests first)

- **Fix from the review of #41:** the topic dialog scrolls in one place (the dialog), not also in its page list.
- **`plan()`** (`services/planning/planner.py`, ADR 0017, "Planner v1 rules"): a pure function of frozen dataclasses.
  - 50-minute blocks with the timer's 10-minute break, 25 only where no 50 fits, on a 5-minute grid.
  - Three passes, sooner deadlines first: a final review in the last 3 days (as late as fits), two blocks per topic
    on different days (as early as fits), then the rest of the workload, spread over days.
  - Each block has a machine-readable reason, and the plan lists shortfalls for task 3's feasibility report.
- **Property tests first** (Hypothesis, a dev dependency, MPL-2.0; the licence check accepts it), committed before
  `plan()`. What failed first:
  - the strategy itself: on the first green run, spacing was only exercised in 0.3 % of examples. A "roomy" mode
    (windows every day, deadlines 2+ days out) brought it to about 22 % and reviews to about 50 %;
  - then **no overlaps**: free time over local midnight is split by day, and each day only checked its own blocks, so a
    block ended 23:55 and the next began 00:00. A day now sees its neighbours' blocks.
  - "time allows" for spacing first meant two days that each fit every topic, which never held in the scenario
    (evenings hold 2 blocks). It is now Hall's condition (ADR 0017), and held over 3,000 examples.
  - Mutations (no cap check, no different-day rule, no reviews) are each caught.
- **Scenario** (2 modules, exams in 10 and 20 days, 12 h a week): every property holds, every topic is spaced, the
  reviews sit on the last free evening before each exam, and the one shortfall is A4's "no estimate". Skipping a block
  re-places its topic's time. 60 topics over 30 days plan in about 5 ms (the test allows 200).
- **Next:** task 3, the feasibility report, the study-method rules table and the reason text.

## 2026-11-20: Phase 4, task 1 (availability, workload and starting confidence)

- **Data** (migration 0021):
  - `users.timezone` (IANA, default Africa/Johannesburg) and `daily_study_cap_minutes` (180).
  - `availability_rules`: weekly windows in local minutes, never across midnight. Overlaps are refused by an
    exclusion constraint (`btree_gist`).
  - `availability_exceptions`: one per date, unavailable or its own windows, with a note.
  - `topics.estimated_minutes` (the student's figure) and `confidence` (1-5, self-rated).
- **Pure helpers** (`services/planning/`):
  - `expand()` gives UTC intervals per local date, exceptions over rules, DST-safe. It's tested in Europe/London:
    00:30-03:00 is 1 h 30 in spring and 3 h 30 in autumn.
  - The daily cap limits what's available, not the intervals.
  - The workload estimate is 3 min a slide and 6 a page of text (ADR 0016), computed, never stored, and labelled.
- **API:**
  - CRUD for rules and exceptions, `GET /availability?from=&to=`, `GET/PATCH /planning/settings` and
    `PATCH /topics/{id}/planning`.
  - The topic tree carries confidence and workload.
  - Every endpoint has a cross-user case.
- **UI:**
  - Settings → Study time: a weekly editor, the cap and timezone, exceptions, and "≈ 4 h a week available (from
    your rules) · ≈ 1 h in the next 7 days".
  - Topics: confidence and workload in the topic's detail; the row shows them on hover or focus.
- **Tests:** 31 pure, 32 API (plus the cross-user cases), Vitest for the Study time and topic flows, and
  `e2e/study-time.spec.ts` (two windows, an exception, and the week's total changes).
- **Next:** task 2, the pure `plan()` with property tests. It must handle topics with no workload estimate.

## 2026-11-19: Phase 3, task 5 (voice: on-device STT, local TTS, push-to-talk, latency), and two fixes from the review of #39

- **Fixes:**
  - **a. Tutor eval answer key** (pages read first):
    - Q3 now also accepts Chapter3 Study Notes p8, which covers salting fully. p9 is about cracking and mentions
      salts in one line, so it isn't added.
    - Q20 now also accepts Chapter1 Study Notes p4 and Final Study Guide p33 and p14.
    - `--rescore` scored run 1 again from its JSON with no AI calls: **18/20 → 20/20** cite an acceptable page, and
      mean coverage **0.88 → 0.91** (now over 20 questions).
  - **b. The quiz prompt** asks only questions whose answer a source states explicitly, so nothing is "more common"
    unless a source says so.
- **Voice** (ADR 0015, "Voice is on-device only"):
  - `voice/stt.ts` uses on-device Web Speech only: `available()`, then a "Set up voice" `install()` when the pack is
    downloadable. `processLocally = true` is set on every recognition, with no server fallback; a browser without
    the on-device API gets no mic, and one line says typing works.
  - Push-to-talk: hold the mic, or hold Space outside a text field or a focused control. "Listening…" shows the
    words so far, and Escape cancels.
  - `voice/tts.ts` uses local voices only and speaks sentence by sentence while the answer streams. Markdown,
    citations, tables and code are left out. "Read aloud" is off by default and kept per browser, and a question
    asked by voice is always read aloud.
  - **Latency:** from release to the first spoken word, with its parts. It's shown as "spoken after X s
    (measured)" and stored by migration 0020 with `PATCH /messages/{id}/voice-timing` (user-scoped, with a
    cross-user case).
- **Tests:**
  - 21 unit tests (`src/voice/voice.test.ts`) and 11 panel tests (`TutorVoice.test.tsx`), all with the fakes in
    `src/test/fakeSpeech.ts`.
  - 6 API tests (`tests/tutor/test_voice_timing.py`) and a quiz prompt test.
  - `e2e/voice.spec.ts`, with the browser's speech faked by `addInitScript`.
- **Browser check (this machine):**
  - Edge 157 says `unavailable` for en-GB and en-US, and Playwright's Chromium 158 says `downloadable`. Chrome isn't
    installed.
  - So the 2.5 s target hasn't been measured on a real device yet. The first spoken question in Chrome or Edge
    with the pack will show it.
- **Next:** measure voice latency on a device with the speech pack, then Phase 3 is done.

## 2026-11-19: Phase 3, task 6 (`evals/tutor`), done before task 5 by decision, and two fixes from the review of #38

- **Fixes:**
  - **a. Interactive JSON repairs** (ADR 0014, amending 0013): the repair goes to the model that wrote the reply.
    If that model turns it away (429, 503, 413, a timeout, a cooldown or its budget), the next models get the
    original prompt afresh, never the first model's reply. A 5xx still fails at once, and background jobs are
    unchanged. 9 tests.
  - **b. Quiz results** mark each question Right or Wrong in words, with the student's pick beside the correct
    option.
- **`evals/tutor`** (`python -m evals.tutor cos330`):
  - The 15 search-eval questions and 5 new ones, each with its topic, go through the tutor's own service in answer
    mode, as a dry run. "Quiz me" follows Q5, Q12, Q16, Q17 and Q18.
  - Calls are paced under Groq's 8,000 tokens a minute.
  - Results are in `apps/api/evals/results/tutor-2026-11-19-run1.json` and `tutor-2026-11-19.md`: numbers,
    labels and pages only.
  - The metrics (coverage, rate, nearest-rank percentiles, "doesn't cover") are unit-tested.
- **Run 1:**
  - 26 free-tier calls: 25 ok and 1 `invalid_json` (repaired on the same model). None was turned away, and pacing
    waited 900 s.

  | Measure                                 | Result                                                                | Target      |
  | --------------------------------------- | --------------------------------------------------------------------- | ----------- |
  | Correct-page citation rate              | **18 / 20 (90 %)**                                                    | ≥ 85 % (17) |
  | Mean coverage                           | **0.88** (19 questions; Q20 had no acceptable page among its sources) |             |
  | "Doesn't cover" answers / failed        | 0 / 0                                                                 |             |
  | Time to first token, median / p90 / max | **654 / 1,342 / 1,530 ms**                                            | under 2 s   |
  | Model                                   | `groq/openai/gpt-oss-120b`, 20 of 20                                  |             |
  - **The misses:** Q3 is a citation choice (CH03 p14 was S2 but not cited). Q20 is a retrieval miss (CH01 p6 and
    p7 weren't among the 8 sources).
  - **No second run.** The targets were met, so the prompt wasn't changed and nothing was tuned against these 20
    questions.

- **Quiz check** (by hand, against the cited pages):
  - The JSON was valid on the first try in 4 of 5 quizzes, and no questions were dropped.
  - The marked answer was supported in 13 of 15 questions:
    - after Q12, Q2: CH09 p10 doesn't say which default policy is more common;
    - after Q16, Q1: by CH09 p27 the marked topology isn't the DMZ one.
  - A wrong option was also true in 1 of 15 (that same Q12 Q2).
  - The #38 prompt change held for the question that prompted it.
  - One explanation cites `[S9]`, which wasn't a source.
- **Phase 3 verify criteria:**
  - **At least 85 % of eval answers cite a correct page:** met (90 %).
  - **Time to first token under 2 s:** met (p90 1,342 ms).
  - **Speech starts within 2.5 s:** waits for task 5 (voice).
- **Next:** Phase 3 task 5: `voice/stt.ts` and `voice/tts.ts`, push-to-talk, latency timing.

## 2026-11-19: Phase 3, task 4 ("Explain differently", "Give an example", "Quiz me"), and five fixes from the review of #37

- **Fixes from the live review:**
  - **a. Chips remounted on every timer tick** (focus lost, tooltips flickering). The cause was react-markdown's
    `components` built inline. They're now defined once, and `TutorDock` is memoised. Two tests (same DOM node,
    focus kept across ticks) fail on the old code.
  - **b. Wide tables** scroll in their own box with readable columns. The prompt prefers lists and keeps tables to 3
    columns.
  - **c. Citations are always bracketed**, tables included; the parser is unchanged.
  - **d. Phones:** the control bar fits one row at 375 px, and the page keeps 8 rem (plus the safe area) for the Tutor
    button. Checked in the 375 px QA capture.
  - **e. Deleting a study session** now deletes its conversation, messages and sources (migration 0019; the FK was
    SET NULL). Conversations orphaned before 0019 aren't touched: they can't be told apart from ones made without a
    session.
- **Modes:** three quiet buttons under the latest finished answer, disabled while a request runs. Explain and Example
  stream on the same sources.
- **Quiz me:**
  - `POST /conversations/{id}/quiz` uses `complete_json` with the `Quiz` schema (one repair, interactive), on the
    last answer's sources only. Ungrounded questions are dropped.
  - It's stored in `messages.quiz`; picks go through `PATCH /messages/{id}/quiz-answers`. Grading is done by code,
    and there are no mastery or plan changes.
  - The panel shows one question at a time with the explanation's chips, Next and the results, and restores after a
    reload.
  - `quiz` is no longer a streamed mode (422 on the stream), and quizzes aren't history. Cross-user cases cover both
    endpoints, and `npm run gen:api` was run.
- **Real check** (`app.tutor.ask --dry-run --after <query> --mode …`, COS330, each query with its topic, all answered
  by `groq/openai/gpt-oss-120b`):

  | After                          | Mode                | Time               | Quiz questions: is the correct answer supported by the cited page?                                                                                                                                                                                 |
  | ------------------------------ | ------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | 5 (inference)                  | Explain differently | first token 764 ms |                                                                                                                                                                                                                                                    |
  | 5                              | Give an example     | first token 531 ms |                                                                                                                                                                                                                                                    |
  | 5                              | Quiz me             | total 1,796 ms     | Q1 yes (notes p14: Start-Date in Salaries lets a Clerk infer names). Q2 yes (guide p19, CH05 p29: detection at query time denies or alters). Q3 yes (notes p20: views don't prevent inference), though "aggregated queries" leans on Ch1 notes p10 |
  | 12 (stateful vs packet filter) | Explain differently | first token 547 ms |                                                                                                                                                                                                                                                    |
  | 12                             | Give an example     | first token 703 ms |                                                                                                                                                                                                                                                    |
  | 12                             | Quiz me             | total 1,077 ms     | Q1: the answer is right (CH09 p14), **but distractor C ("inspects FTP and SIPS commands") is also true by p14**. Q2 yes (p10). Q3 yes (p6)                                                                                                         |
  - **The first query-5 quiz failed.** It ran right after the other two modes: Groq returned invalid JSON twice, the
    repair hit Groq's minute limit, and Flash-Lite's reply was invalid too. I couldn't tell why: the CLI didn't print
    the usage details yet. It does now.
  - **A retry right away was turned away** (`AIUnavailable`), and the CLI now reports that instead of crashing.
  - Spaced two minutes apart, both quizzes worked first time, with 0 questions dropped.
  - **About 20 free-tier calls** in all, every one on Groq except one Flash-Lite repair.
  - The quiz prompt now asks the model to check every wrong option against the sources. That isn't re-measured.

- **Tests:**
  - **API:** 26 for the quiz (schema, repair, ungrounded, fewer than 3, none grounded, 422 before an answer, 503
    without waiting, not history, not streamed, answers saved, bad answers rejected); 3 for the session cascade;
    2 new cross-user cases; 1 CLI quiz.
  - **Web:** 10 new (2 for chip stability, 8 for the quiz flow).
  - **e2e:** `tutor-modes.spec.ts` asks, explains, quizzes, answers all three and reloads. It has no AI fakes in the
    app: the tutor API is answered by `page.route` over a small in-memory record.
- **Screenshots:** a new `quiz-{light,dark}.png` (the demo seed's fixture quiz on the NET201 slides) and the session
  shot back on the answer, both regenerated in both themes. They're in the README gallery.
- **Vitest note:** a direct `npx vitest run` from `apps/web` hung three times with no output. Every folder passed
  alone, and `npm run check`'s vitest step passed in 26 s.
- **Migration 0019 isn't applied to the dev database.** Run `npm run db:migrate`.
- **Next:** Phase 3 task 5: `voice/stt.ts` and `voice/tts.ts`, push-to-talk, latency timing.

## 2026-11-19: Phase 3, task 3 (the tutor panel), and three fixes from the live review of #36

- **Backend fixes:**
  - **Follow-ups keep their sources.** `explain_differently`, `example` and `quiz` reuse the last answer's sources,
    with the same labels. That needs `message_sources.chunk_id` (migration 0018, which also adds
    `UNIQUE (id, user_id)` on chunks); a lost chunk falls back to its page's first chunk.
  - **A new question in a conversation searches twice:** on its own words, and on the previous question plus its own,
    fused by RRF.
  - **The embedding model loads at startup** in the API (a background thread from its lifespan) and the worker
    (`PRELOAD_EMBEDDER`).
  - **`GET /modules/{id}/tutor/conversations?study_session_id=`**, with cross-user cases. `npm run gen:api` was run.
  - The CLI has `--after QUESTION`, for a follow-up in a dry run.
- **The panel** (`features/tutor/`, ARCHITECTURE "The tutor panel", DESIGN "Tutor panel"):
  - **Layout:** a collapsible right-hand panel from 1024 px (the timer's column stays at least 480 px); a glass
    bottom sheet on phones. One conversation per session, restored after a reload.
  - **Answers:** streamed with a caret and Stop. Markdown and KaTeX are lazy-loaded, raw HTML is never rendered, and
    KaTeX runs with `trust: false`.
  - **Citations:** `[S1]` and `【S1】` chips with a tooltip; clicking opens the viewer at that page. Cited sources come
    first and the rest are folded. The footnote reads "Answered by gpt-oss-120b (Groq) · first words in 0.6 s
    (measured)".
  - **Errors** are readable ("The free AI providers are busy; try again at HH:MM"), with Retry.
  - **Accessibility:** a polite live region by sentence, Enter to send, and the first-use privacy note.
  - Room is left for task 4's buttons and task 5's voice.
- **Dependencies (MIT):** react-markdown, remark-gfm, remark-math, rehype-katex and katex. The licence check
  passes (225 npm packages ok).
  - An npm override pins every katex copy to 0.19.1, because rehype-katex and micromark-extension-math asked for
    0.16 (GHSA-238p-pmpm-9mq7, low).
  - `npm audit --omit=dev` finds 0.
- **Bundle:**

  |                                                           | Before                  | After                                              |
  | --------------------------------------------------------- | ----------------------- | -------------------------------------------------- |
  | Main JS                                                   | 637.28 kB (196.02 gzip) | 663.84 kB (204.03 gzip)                            |
  | Main CSS                                                  | 52.40 kB (10.71 gzip)   | 57.57 kB (11.70 gzip)                              |
  | Lazy Markdown and KaTeX chunk, loaded on the first answer | —                       | 440.10 kB (132.47 gzip) + CSS 29.80 kB (7.97 gzip) |

- **Eval follow-ups** (`evals/search --retrieval`): an acceptable page in the 8 for 3 of 3 with context, against 2 of 3
  searched alone. The table is in `evals/README.md`.
- **Real check** (`app.tutor.ask --dry-run --after …`, COS330, 8 free-tier calls, all `groq/openai/gpt-oss-120b`):

  | Case                                                                                   | Sources                                         | Cited                                                 | First token |
  | -------------------------------------------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------- | ----------- |
  | The live bug: "Explain that differently…" after the stateful-vs-packet-filter question | the earlier answer's 8, all CH09                | CH09 p14, p10                                         | 625 ms      |
  | "how can a database stop that?" after query 5                                          | Ch5 notes p20, p14, guide p19, CH05 p29…        | p20, notes p14, guide p19, CH05 p29                   | 735 ms      |
  | "which of the two is faster?" after query 12                                           | CH09 p14, p13 among the 8 (S1 is Ch7 notes p38) | none: "the material doesn't cover their speed" (true) | 1,483 ms    |
  | "which one leaves the customer responsible for the most?" after query 15               | CH13 p15, p14, p13…                             | CH13 p15, p14, p13                                    | 531 ms      |

- **Tests:**
  - **API:** 14 for follow-ups, the list endpoint and preloading; 2 new cross-user cases; 1 for the CLI.
  - **Web:** 41 new (SSE parser 7, citations and turns 8, Markdown and KaTeX safety 19, panel 14); 405 in all.
  - **e2e:** `tutor.spec.ts` (page.route fixture). `npm run e2e -- --repeat-each=3` passed 12 of 12.
- **Screenshots:** the session shot now has the panel open, on a fixture exchange in the demo seed (synthetic NET201,
  never COS330). It was regenerated in both themes.
- **Migrations 0017 and 0018 aren't applied to the dev database.** Run `npm run db:migrate` before using the panel.
- **Next:** Phase 3 task 4: "Explain differently", "Give an example", "Quiz me" (3 questions).

## 2026-11-19: Phase 3, task 2 (SSE tutor endpoint and conversation storage)

- **Done:**
  - **Streaming:** `LLMClient.stream_text` and the adapter's `stream` (SSE over httpx), with ADR 0013's rules.
    - Fallback happens only before the first answer token, and never after it.
    - Interactive calls never wait on a 429 or 503.
    - Thinking deltas are hidden, "length" marks the answer truncated, and stopping the stream is logged as `stopped`.
    - `complete_text`'s failure handling moved into one shared `_after_failure` (behaviour unchanged).
  - **Migration 0017:** `conversations`, `messages` (ordered by `position`) and `message_sources`, all with `user_id`
    and composite FKs; plus the `ai_usage` outcome `stopped`.
  - **Endpoints:** `POST /modules/{id}/tutor/conversations`, `GET /conversations/{id}`, and
    `POST /conversations/{id}/messages`, which streams `sources`, `delta`, then `done` or `error`. It uses FastAPI's
    native SSE, and a dependency returns 404 before the stream opens. `npm run gen:api` was run.
  - **History:** the last 2 answered exchanges go in the prompt, within the context budget (sources first, oldest
    exchange dropped first), with their `[Sn]` labels stripped.
  - **Citations:** parsed when the stream ends; unknown labels are flagged, and the text is never rewritten.
  - **Disconnect:** the provider's stream is stopped and the partial answer is stored as `stopped` (shielded).
  - **CLI:** `python -m app.tutor.ask` (`--dry-run` writes nothing).
  - **Tests:** 23 streaming, 16 HTTP (including a raw-ASGI disconnect), 9 turn and citation, 2 CLI, and 5 new
    cross-user cases.
- **Real check** (dry run, COS330, `--topic` per query, about 70 s apart for Groq's 8K tokens a minute):

  | #   | Question            | First token | Model                    | Cites an acceptable page      |
  | --- | ------------------- | ----------- | ------------------------ | ----------------------------- |
  | 1   | attack surface      | 703 ms      | groq/openai/gpt-oss-120b | yes: notes p15, CH01 p35, p36 |
  | 5   | inference           | 827 ms      | groq/openai/gpt-oss-120b | yes: Ch5 notes p14            |
  | 9   | SYN spoofing        | 843 ms      | groq/openai/gpt-oss-120b | yes: Ch7 notes p9             |
  | 12  | stateful inspection | 828 ms      | groq/openai/gpt-oss-120b | yes: CH09 p14                 |
  | 15  | IaaS / PaaS / SaaS  | 796 ms      | groq/openai/gpt-oss-120b | yes: CH13 p13, 14, 15         |
  - Free-tier calls: 6, all `groq/openai/gpt-oss-120b`, all ok. That's these 5 plus a first run of question 1, which
    found the citation bug below.
  - Times are measured from receiving the question, and include retrieval (46–77 ms). Loading the embedding model
    (about 850 ms, once per API process) isn't counted.
  - The first run of question 1 took 3,687 ms, with a cold model load and the old prompt.

- **Found on real data:**
  - gpt-oss cites in full-width brackets, `【S1】`: 3 of 5 answers did, even after the prompt asked for `[S1]`. The
    first run parsed no citations at all.
  - The parser and the history stripping now accept both forms. The text is stored as written, so task 3 must render
    `【Sn】` as a citation too.
- **Decided (ADR 0013):**
  - Interactive calls never wait, and there's no fallback after the first token.
  - Failed and stopped answers are kept with their partial text, but don't count as history.
  - `message_sources` copies the titles, so a deleted material leaves the citation readable.
- **Migration 0017 isn't applied to the dev database.** Run `npm run db:migrate` before using the endpoints or the
  CLI without `--dry-run`.
- **Next:** Phase 3 task 3: the tutor panel (streamed answers, clickable [S1]–[S8] citations into the viewer, KaTeX).

## 2026-11-18: Phase 3, task 1 (tutor retrieval and prompt templates)

- **Done:**
  - `app/services/tutor/retrieval.py` `retrieve`: the module's hybrid search (all fused candidates), then a topic
    boost, `allow_ai` only (through `chunks_for_prompt`, which now also returns the page title), one source per page,
    at most 8, a token budget that drops the lowest-ranked first, and labels S1–S8 in rank order. No provider calls.
  - `app/services/tutor/prompts.py`: the system prompt, `<material id="S1" title="…" page="…">` blocks (a `<material`
    inside a passage is escaped), and the four modes (answer, explain differently, example, quiz with 3 questions).
    `UNTRUSTED` moved to `app/ai/sources.py` so both prompt sets share it.
  - **Linking threshold 0.75** (was 0.63), with migration 0016 queuing a relink (not run on the dev database). The
    real-model fixture test now checks the fixtures at their own 0.63 and that no unrelated passage reaches 0.75.
  - `evals/search --retrieval`, with each query's topic in `search/cos330.yaml`.
  - #34 review: search result and page-list titles strip Markdown ("… essay _(Ch5, 5 marks)_" → "… essay (Ch5,
    5 marks)"). The session's Materials link and tutor note were already below the timer; the flow test now asserts
    the order and the link (checked in tests; no dev server was running to look at it).
  - Tests: 16 retrieval (cross-user module and topic, a topic from another module, `allow_ai`, one per page, the cap,
    labels, the budget, the boost only on linked chunks and subtopics), 11 prompt, the 0016 migration, 2 web.
- **Eval (COS330, 15 queries, links as built at 0.63):**
  - No topic: an acceptable page in the 8 for 15/15, at S1 for 12/15, MRR 0.900, 30 acceptable pages in the 8.
  - The query's topic at ×1.25, ×1.5 or ×2: unchanged ranks, 32 acceptable pages in the 8. At ×3: 33.
    Counting only links ≥ 0.75 gives the same.
  - A topic from another chapter: S1 for 11/15 at ×1.25 (MRR 0.867), and 9/15 at ×1.5 or more (MRR 0.800 / 0.800
    / 0.789). The acceptable page stayed in the 8 for 15/15 in every run.
  - Context: 918–3,530 estimated tokens (mean 2,063), under the 4,500 budget, so nothing was dropped.
- **Decided:**
  - `TUTOR_TOPIC_BOOST` = 1.25 (×1.5's and ×2's on-topic gain, at the smallest off-topic cost), multiplying the
    fused RRF score.
  - `TUTOR_CONTEXT_MAX_TOKENS` = 4,500 at 3.5 characters a token for course prose (it ran at about 4.6, decision
    0010). With about 600 for the prompts and 2,000 for the answer, a full request stays under Groq's 8,000 a minute.
  - The boost reads `chunk_topics`, not `topic_pages` directly: it already holds the cited pages, less the ones the
    student unlinked.
- **Next:** Phase 3 task 2: the SSE tutor endpoint, plus `conversations` / `messages` storage with citations.

## 2026-11-18: Glass polish, and the e2e failure on main

- **CI on main was red** (run 44321451301: the e2e job's "a PDF opens from a search result" failed after #33 merged,
  though it passed on the PR; seen once locally before #33 too).
  - **Root cause:** a race in the viewer, not in the test. `PdfPage` kept "drawing" as state that it only set to true
    in an effect, after React had committed the new page. For one commit after turning from page 3 to page 1, the page
    region read "Page 1, aria-busy false" with page 3's stale state. The test's wait for `aria-busy="false"` passed at
    once, the effect then started drawing (which clears the canvas), and the canvas check read a blank canvas.
  - A second window: when a drawn page grew tall enough to need the box's scrollbar, the box narrowed and the page was
    redrawn.
  - **Fix:** busy is derived from what was last drawn completely (page, zoom and size), so a new page is busy from its
    first commit. Fit page has a fixed-height box that never scrolls; Fit width reserves its scrollbar space.
  - A regression test reads the region in every commit (a React Profiler) and fails on the old component.
  - No sleeps or retries.
- **CI:** checkout v7, setup-node v7, cache v5, upload-artifact v7, setup-uv v10 (all Node 24); every job pinned to
  `ubuntu-24.04`. "CI passed" is still the only required check.
- **Polish:**
  - **Badges:** violet with an ink label. The CI badge keeps shields.io's status colour, so failures still show red.
  - **Search results:** led by "title · page N", with the snippet clamped below. Markdown is stripped for display, one
    result per page shows "N matches on this page", and the API is unchanged.
  - **Viewer:** Fit page (the default, no scrollbars) and Fit width.
  - **Topic tree:** chapter rows are bolder than subtopic rows. Row actions show on hover or focus, and sit in a "…"
    menu on touch screens.
  - **Module header:** Edit and Delete moved into a "…" menu.
  - **Layout:** one 1120 px container for every page.
  - **Today:** "Next up" now says "Start a session on any module."; "Your day" is a compact empty state instead of an
    empty hour grid.
  - **Phones:** a glass bottom tab bar under 640 px, with the wordmark staying at the top.
  - **Materials rows:** each fact said once.
  - **Settings:** Appearance first.
  - **Navigation glass:** stronger (`glass-nav`, 0.92 / 0.94 tint and 36 px blur; checked in `tokens.test.ts`).
  - **Session:** one centred column, with a small card for Materials and the tutor note.
- **Tests changed** (only where markup or copy changed):
  - module Edit and Delete are opened from the menu;
  - search hits are asserted by title and page, in the unit test and in two e2e lines;
  - the ready chip says "Ready", and the scanned count appears once;
  - Today asserts no hour grid and the new Next-up line.
- **New tests:** the viewer race, Fit page / Fit width, Markdown stripping and grouping (11), one result per page, and
  the topic "…" menu.
- **Repeat run:** `npm run e2e -- --repeat-each=10`: **30 of 30 passed** (3 tests × 10). Getting there exposed two
  problems with the tests themselves, now fixed with no sleeps or retries:
  - **Fixed module codes:** a repeat reuses the database, so each run's module code now gets a suffix
    (`uniqueCode`, e.g. `MAT101-R3`).
  - **Paused clock too early:** the session spec paused its fake clock before opening the start dialog. The app's data
    layer delivers results through timers, so switching to this run's module (when an earlier run's module was the
    default) never showed its topics. The clock now runs until the dialog is filled, then pauses before Start.
  - Also, the first search of a run waits for its own result (the API loads the embedding model on first use) instead
    of the default 5 s.

## 2026-11-18: Visual direction C "Glass" (decision 0012)

- **Done:**
  - Every screen restyled from Planner to Glass, presentation only (behaviour, routes, API calls and test intent
    unchanged).
  - `docs/DESIGN.md` rewritten as the spec; the old one archived at `docs/archive/DESIGN-planner.md`; ADR 0012.
  - **Tokens:** one source in `index.css` (CSS variables per `data-theme`, mapped into Tailwind v4). Light and dark,
    an Appearance setting (System, Light, Dark) in Settings, and an inline script in `index.html` so the theme is set
    before the first paint.
  - **Glass:** selective; only the nav, dialogs, the ReviewBar, the session control bar and the Today hero's text
    layer.
  - **Fonts:** Inter only; Space Grotesk removed.
  - **Screens:** a gradient hero on Today with its text on glass; a gradient progress ring and ambient mist on the
    session screen; skeleton loaders; designed empty states for Plan, Practice and Insights. The session screen's stale
    "Materials arrive in Phase 2" copy now describes what exists.
  - **Assets:** banners and social previews (light and dark) and all README screenshots regenerated in both themes;
    the README uses `<picture>` for each. The Mermaid classes are now pink for AI, pale violet for code, white for
    storage.
- **Measured:**
  - `tokens.test.ts` computes WCAG contrast from the stylesheet for every text and control pair in both themes,
    including glass over its worst-case backdrop.
  - The test caught three things, which the tokens now fix:
    - The input-border token was under 3:1 (2.98).
    - The violet button's boundary on dark surfaces was 2.88:1, hence a `primary-edge`.
    - The spec's glass tint (0.62 / 0.55) fails 4.5:1 for muted text over dark content, hence `glass-strong` at 0.86
      for glass that can float over anything.
  - Text never sits on the gradient: dark text drops to 3.35:1 at the violet end, white to 2.54:1 at the pink end.
  - Bundle: main JS 575.7 → 594.1 kB (gzipped 175.8 → 181.2), CSS 34.7 → 47.8 kB (7.5 → 10.1); Space Grotesk's 12 font
    files (about 137 kB) gone.
  - Module colours unchanged (they pass on both canvases), so no migration.
- **Tests changed** (only where markup or copy changed):
  - The nearest countdown tile is now asserted by `data-nearest`, not its old `border-ink` class.
  - The session Materials copy assertion follows the corrected text.
  - The too-dark custom colour now measures 3.4:1, not 3.3:1, because the dark text on fills moved from `#111111` to
    `#0B0B12`; it's still rejected.
- **New tests:** appearance (storage, resolve, apply, blocked storage); the Settings appearance group; token contrast.
- **QA:** every screen in light and dark at 1440, 768 and 375 px (`npm run screenshots -- --qa`, 90 shots) was reviewed.
  One fix came out of it: the mobile nav row now fades at its right edge, so it reads as scrollable.
- **Observed:** one of four local e2e runs failed the pdf.js canvas check after jumping to page 1; the next three full
  runs passed. Watch for it in CI.
- **Next:** upload `docs/assets/social-preview.png` as the GitHub social preview; then Phase 3.

## 2026-11-18: Repository presentation (README, assets, screenshots, docs, redaction)

- **Done:**
  - A new README: banner, summary, three badges, the Today screenshot, a "What it does" table, four screenshots,
    engineering highlights, a Mermaid architecture diagram (checked in light and dark with mermaid-cli), the status
    table, run instructions and the docs table.
  - `npm run assets` renders the banners (3200×800, light and dark) and the social preview (1280×640) from
    `docs/assets/src/banner.html` with the self-hosted fonts.
  - `npm run screenshots` runs its own stack and `studysensei_demo` database. It seeds the synthetic NET201 module
    (`apps/api/scripts/demo_seed.py`: original text; 3 materials through the real pipeline, 6 jobs, no AI calls;
    6 sessions; 9 topics; 57 chunk links), shoots Today, a session, Topics and the viewer at 1440×900 ×2 with the date
    fixed to Mon 16 Nov 2026 10:40, and tears down. Both scripts ran clean from a dropped database.
  - `tests/fixtures/make_fixtures.py` gained `slide_deck_pdf` and `notes_docx`; `_pdf` still writes byte-identical
    fixtures.
  - `docs/README.md` (hub), `docs/decisions/README.md` (ADR index), and `npm run links`: 72 relative links and images
    in 23 files resolve.
  - `docs/PLAN.md` and `docs/PROJECT_HANDOVER.md` moved to `docs/archive/` with an "Archived. Personal identifiers
    redacted" note; links fixed.
  - Personal identifiers redacted from tracked files (except `docs/AUTHORSHIP.md`, on purpose): the former owner name
    is now Joshua or "the owner", and the student number and local paths are gone. The course-material path and the
    submissions' file pattern now live in the gitignored `CLAUDE.local.md`. Git history isn't rewritten.
- **Sources for the README's figures:**
  - 155 and 15 AI calls: ADRs 0007 and 0008.
  - Search 15 of 15 in the top 3, slide 11 of 15, MRR 0.900: `apps/api/evals/README.md`.
  - CI 1.5 minutes: PR #31's run.
  - 603, 304 and 3 tests: this branch's `npm run check`, and the two Playwright specs.
- **Found:**
  - There's a `v0.2.0` tag but no GitHub release, so the README links the tag.
  - The session screen's Materials panel still says "Materials arrive in Phase 2". That's app copy, left for a fix PR.
- **Next:** set the social preview in GitHub settings (upload `docs/assets/social-preview.png`); fix the stale
  session-screen copy; then Phase 3.

## 2026-11-18: Spike S1, a camera measurement page (not yet run)

- **Done:**
  - `apps/web/spikes/s1-camera/`, served by `npm run spike:s1` on :5175. It has its own Vite entry, and is linted,
    type-checked (`tsconfig.spikes.json`) and tested with the web app, but it's not in the app's bundle or routes.
  - It asks for the camera once, then runs one mode at a time on the same workload: frames scaled to 160×120, mean
    brightness and frame difference, no ML. The modes are: (a) `requestVideoFrameCallback`; (b) `setInterval` at
    100 ms; (c) a worker fed by `MediaStreamTrackProcessor` with the track transferred in; (d) c plus Document
    Picture-in-Picture; (e) c plus a held Web Lock.
  - A protocol panel with clock times and a countdown: 30 s visible, 60 s on another tab, 60 s minimised, 30 s
    visible again.
  - Frame times, visibility and PiP changes are stored as timestamps and turned into per-second samples when a run
    ends, so throttled page timers can't distort them. The results JSON adds the browser, OS, mode and a per-phase
    summary.
  - Vitest covers the pure parts: aggregation, phase marking and the workload. No camera runs in CI.
- **Decided:**
  - Mode e uses a Web Lock: Chrome's freezing heuristics document that it exempts a page. It's flagged as a risk,
    because it's a heuristic, not a guarantee.
  - No audible-silence trick, because it isn't documented and real audio would change the measurement.
  - No Tauri work.
- **Next:** Joshua runs all five modes on his laptop and sends the five JSON files. The results are reviewed, then
  S1 is decided (and ticked, with an ADR). S1 stays unticked until then.

## 2026-11-18: Ownership, licence and third-party notices (docs)

- **Done:**
  - `LICENSE` (all rights reserved, Joshua Heath), and an "Ownership and licence" section in the README.
  - `docs/AUTHORSHIP.md`, a dated record of how StudySensei is made.
  - `.github/CODEOWNERS` (`* @Josh-Heath123`; code-owner review stays optional).
  - `CHANGELOG.md` with one entry per phase (0: #1, 1: #2–#11, 2: #12–#28), and an Ownership note in CLAUDE.md.
  - `THIRD_PARTY_NOTICES.md`, generated by `npm run licenses` from `scripts/license-data.mjs`, the data the licence
    check uses. It lists 59 Python and 107 npm production packages, plus the embedding model and the fonts. CI's
    hygiene job fails if the file is stale.
- **Checked:**
  - bge-small-en-v1.5 is MIT on its model card, and so is the ONNX copy fastembed downloads (Qdrant).
  - Inter and Space Grotesk are OFL-1.1, per the LICENSE files their packages ship.
  - Anthropic's consumer terms are effective 8 Oct 2025, and the outputs sentence is quoted verbatim.
  - The history has 7 commits from the university address (19–26 Jan 2026) and 187 from the personal one.
- **Found:**
  - The owner's own commits aren't signed. Only GitHub's merge commits and the initial commit carry a verified
    signature, so AUTHORSHIP says so rather than calling the history signed. `main-signed.json` is ready for when
    signing is set up.
  - The npm licence check now reads package-lock.json: 107 production packages, against 97 before. The 10 extra are
    the other platforms' `@napi-rs/canvas` builds, which `npm query` missed because they aren't installed here.
  - The hygiene job no longer runs `npm ci`.
- **Next:** spike S1 (camera in the browser).

## 2026-11-18: CI as the merge gate; faster CI and local check (infrastructure)

- **Measured before:**
  - CI, last 10 PR runs: median wall 2.07 min (1.6–2.6). Slowest steps: pytest 23–45 s, vitest 32–63 s,
    `npm ci` 8–54 s (uncached node_modules), Playwright 24–49 s, Chromium install 13–33 s, service containers 11–18 s.
  - Local `check:steps` (serial, warm caches): ruff 2.6 s, ruff format 0.1 s, prettier 3.1 s, eslint 9.7 s, mypy 2.1 s,
    tsc 7.9 s, pytest 81.4 s, vitest 31.8 s; 138.8 s in total. Vitest once hung locally for 48 minutes and held the
    check lock, failing every check after it.
- **Done:**
  - **CI passed**, the one job a ruleset will require: it needs every job, runs always, and fails if any failed or was
    cancelled. A `changes` job (`dorny/paths-filter`) skips api, web and e2e for Markdown/`docs/`-only changes. The
    push trigger no longer lists `rebuild`.
  - **hygiene** job, always: gitleaks 8.30.1 (checksum-verified) over the PR's commits; `scripts/check-licenses.mjs` over
    the Python environment (73 packages) and npm production dependencies (97). One reviewed exception:
    `py-rust-stemmers` ships an MIT licence file but no metadata. A full-history gitleaks scan found one hit, a fake test
    key that looked real (`PING_GROQ_KEY`); the fake keys now look fake. The dev DB password didn't trip.
  - Faster: pytest on 4 xdist workers, each with its own `studysensei_gwN_test` database (the `_test` guard stays);
    vitest on the `vmThreads` pool; `node_modules` and Playwright browsers cached.
  - `scripts/check.mjs`: two parallel phases (static steps with Postgres starting, then pytest and vitest), per-step
    time limits that kill a hung step, logs in `.locks/check/`, a failed step's log tail under its name, and timings.
    `with-lock.mjs` also takes over a lock held for more than 20 minutes (an orphan).
  - Rulesets as code (`.github/rulesets/main.json`, `main-signed.json`) and CONTRIBUTING.md on applying them; not applied.
  - CLAUDE.md: run the check in the foreground with a 10-minute timeout, never end a turn with a check, push or CI pending.
- **After, local:** `npm run check` 64.4–66.0 s wall (pytest 50 s and vitest 23 s in parallel); `check:serial` 89.2 s
  (pytest 37.4 s, vitest 19.7 s, eslint 14.1 s, tsc 9.3 s).
- **After, CI** (PR #29's first full run, node_modules cached, Playwright browsers not yet): wall 2.0 min. e2e 110 s
  (Playwright 47 s, Chromium install 22 s, the cache now saved), api 85 s (pytest 42 s), web 68 s (vitest 20 s, no
  `npm ci`), hygiene 22 s, changes 6 s. The wall was already under the 5-minute target; it's set by e2e. pytest-xdist
  didn't help on CI's 4 vCPUs (42 s against 23–45 s before: each worker migrates its own database), only locally.
  With both caches warm (the next run): **wall 1.8 min**, 13 % under the old median; e2e 92 s (Chromium restored,
  13 s for its system libraries), web 45 s (vitest 13 s), api 84 s, hygiene 17 s. Not the 40 % cut, but under 5 minutes
  before and after, with no check dropped: what's left is Playwright (38 s) and pytest (40 s) themselves.
- **Fixed a flaky test** CI caught on this PR: `MaterialViewer` "a PDF that won't load falls back to its extracted text"
  checked the page-text region's content as soon as the region appeared, before its text had loaded. It now waits for
  the text.
- **Vitest hang, seen again** during this PR's final check: it printed its header and then nothing, and the new step
  limit killed it after 6 minutes, reported it by name, and released the lock. Six runs on their own (13–17 s each)
  and two more full checks didn't reproduce it; both hangs came while or just after pytest ran. Cause unknown. The
  limit is now 2 minutes (a normal run is about 20 s), and a timed-out vitest is retried once and reported as such; a
  failing test is never retried. Final checks: 53.0 s and 61.0 s.
- **Next:** apply `.github/rulesets/main.json` (CONTRIBUTING.md), then spike S1.

## 2026-11-18: Phase 2, evals for search, linking and topic extraction

- **Done:** `apps/api/evals/` with three runners against the dev database (read-only in Postgres, no AI calls,
  never in CI), the COS330 config (chapter patterns, 15 search queries, the 58-topic reviewed reference as names
  and parent names), pure metrics in `evals/metrics.py` with unit tests in `tests/evals/`, and a README.
  Nothing committed is course text.
- **Search** (`python -m evals.search cos330`): slide in the top 3 for 11/15 (the ROADMAP's 12 isn't met: in all
  four misses, queries 1, 5, 6 and 9, the student's own notes page on that concept ranks first); any acceptable
  page in the top 3 for 15/15, **PASS**; MRR 0.900.
- **Linking** (`python -m evals.linking cos330`), subtopics, which the 18 Nov baseline counts: 551 cited, 310
  similarity (0.67–0.88), 0 on near-empty pages, 201 same-chapter, 91 cross-chapter, 18 study guide. Chapter
  topics: 543 cited, 50 similarity. The local re-score reproduces all 310.
  - Global threshold: 0.67 keeps all; 0.72 keeps 197/75; 0.74 keeps 184/56; **0.75 keeps 176/44** (88 % /
    48 %); 0.76 keeps 158/27 (79 % / 30 %); 0.78 keeps 112/5 (56 % / 5 %).
  - Relative (within δ of the best cited page): δ 0.07 keeps 171/69 (85 % / 76 %), δ 0.05 keeps 142/52. Worse
    than a global threshold at every level. Cap 8 keeps 137/45, cap 6 keeps 109/20.
- **Decided:** no rule clearly wins: none drops most cross-chapter links while keeping 85 % of same-chapter ones, so
  the defaults stay 0.63 and cap 12, and there's no relink migration. If a cut is wanted later, 0.75 is the best
  option within the 85 % bound (it halves cross-chapter links); 0.76 if losing a fifth of same-chapter links is
  acceptable.
- **Topic extraction** (`python -m evals.topic_extraction cos330`): 58/58 matched, 0 missing, 0 extra, 0 moved.
  Citation precision by chapter: slides 716/716, notes 318/319, Ch8 notes 106/106; the study guide's 59 have no
  chapter. The notes' known errors are spill into neighbouring sections of the same chapter, which a chapter check
  can't see.
- **Next:** spike S1 (camera in the browser), then Phase 3. Re-run the evals before and after any prompt, model or
  linking change.

## 2026-11-18: Phase 2, COS330 review and link check

- **Review:** Joshua used Keep all: 53 kept, 0 renamed, 0 merged, 0 dismissed. The Project chat then checked all 53
  against the decks, notes and study guide.
  - Every name holds up, so the ≥ 80 % check passes on content.
  - Two missing subtopics were added by hand: Ch5 "Inference and Inference Detection" and Ch10 "Other Overflow
    Attacks". COS330 now has 58 topics.
- **Links before PR #26:** 869 (551 cited, 318 similarity). 127 similarity links went to pages under 150 characters,
  and 115 crossed chapters.
- **Links after PR #26's relink:** 861 (551 cited, 310 similarity). None go to near-empty pages, and 91 cross
  chapters. Similarity scores run 0.67–0.88, so the 0.63 threshold never limits anything.
- **AI citations:** citations into the decks were all correct in a full check of Ch5, Ch8 and Ch11. Citations into the
  notes and the study guide spill into neighbouring sections: about 26 of 190 were wrong, worst in the Ch8 notes.
- **Checked on real data on 18 Nov:**
  - The viewer (PR #24): search opens CH05 at p29, linked pages open at their page, and the scanned ST1 2016 renders.
  - Settings (PR #25): it matches `/ai/status`. Test keys: 4 models OK, and Gemini 3.8 Flash returned a 503 that
    wasn't counted.
- **Also:** committed `docs/PROJECT_HANDOVER.md` as a dated snapshot; ADR 0011 (large merges are Gemini-only)
  replaces the strict-xfail COS330-sized merge test; docs inconsistencies from the handover fixed.

## 2026-11-18: Phase 2 fix, near-empty pages no longer link by similarity

- **Found** (COS330's links on 18 Nov): 318 similarity links, scored 0.69–0.83. 127 of them (40 %) were pages
  under 150 characters: the deck title slide (98 characters, linked to topics in 8+ chapters), "Chapter N"
  dividers and caption-only slides. 115 similarity links crossed chapters, 77 of them these pages. The 0.63
  threshold never cut anything; the top-12 cap did.
- **Done:**
  - `TOPIC_LINK_MIN_PAGE_CHARS` (default 150): a chunk whose page has less extracted text isn't a similarity
    candidate. Cited pages are unaffected.
  - Migration 0015 (data only) queues `link_topics` for every module with chunk links or a successful merge,
    unless one is already queued. No AI call; unlinks and cited links stay as they are.
  - Threshold and cap unchanged (the evals task decides those).
- **Tests:** a near-empty page with a high score isn't linked; a cited one stays; the relink job keeps unlinks and
  cited links, and gives the student's own topic similarity links; the migration queues one job per module.
- **Next:** after merge and a restart of `npm run dev`, measure COS330's links again; then the evals task.

## 2026-11-18: Phase 2, AI provider settings page

- **Done:**
  - `POST /ai/ping` tests every configured model concurrently and returns one result each: ok with latency, failed
    with the provider's error text, or skipped (budget used up, not called) with the reset time, plus whether the
    model is in the provider's `/models` list. Calls are logged as purpose `ping` against the caller.
  - `app/ai/ping.py` now has one `ping_routes` that returns structured results; the CLI formats them (same lines, plus
    a `skipped` line). `LLMClient.budget_reset` is public so the ping can skip a spent model.
  - Settings replaces its placeholder with "AI providers": key set or not, roles with what uses them, usage meters
    (measured count, estimated budget, local reset time), "Test keys" and the privacy note.
- **Tests:** API (ok, failure text without keys, lost connection, not in `/models`, skipped budget, no providers),
  cross-user (Alice spending Flash's budget doesn't skip Bob's Flash; rows belong to the caller), CLI line format,
  and Vitest for the page. The test usage store now takes a lock, since the ping writes concurrently.
- **Next:** `evals/topic_extraction` and `evals/search` from COS330.

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

## 2026-11-17: Phase 2, topic map fixes after the first COS330 run

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
  - a 10 s connect timeout and a separate 90 s read timeout; a timeout is retryable, logged as `timeout` (migration 0009) and counts against the budget
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
