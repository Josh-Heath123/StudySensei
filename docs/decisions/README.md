# Decisions

Architecture decision records: the context, the decision, the alternatives and the consequences. They're never edited
after they're accepted (apart from redacting personal identifiers); a later record supersedes or amends an earlier one.

| Number | Decision | Status |
| --- | --- | --- |
| [0001](0001-web-rebuild.md) | Rebuild StudySensei as a web app (React and FastAPI, Postgres with pgvector) | Accepted |
| [0002](0002-free-ai-providers.md) | Free-tier AI (Gemini and Groq, optional Ollama) behind one OpenAI-compatible adapter | Accepted |
| [0003](0003-session-event-log.md) | Study sessions are an append-only event log; totals are derived | Accepted |
| [0004](0004-material-storage-and-jobs.md) | Materials stored by content hash; background work runs from a Postgres job queue | Accepted |
| [0005](0005-chunking-and-search.md) | Page-bound 400-token chunks, local bge-small embeddings, exact hybrid search | Accepted |
| [0006](0006-topic-maps.md) | AI topic maps: per-material proposals, one anchored merge, local chunk links | Accepted |
| [0007](0007-bounded-topic-extraction.md) | Bounded, lenient topic extraction: parts, call caps, pacing, no error cascades | Accepted; amends 0006 |
| [0008](0008-busy-models-and-refusals.md) | Busy models and refusals move on to the next model | Accepted; amends 0007 |
| [0009](0009-topic-review.md) | Topic review: the student's edits win, and a merge Groq can take | Accepted; builds on 0006–0008 |
| [0010](0010-merge-token-ratio.md) | The merge's token ratio is 2.5 characters, and an oversized merge is reported, not cut | Accepted; supersedes part of 0009 |
| [0011](0011-large-merges-gemini-only.md) | Large topic-map merges are Gemini-only | Accepted; settles 0010's open question |
| [0012](0012-visual-direction-glass.md) | Visual direction C "Glass" (light and dark, selective glass) | Accepted; supersedes the 13 Nov choice of direction B "Planner" |
| [0013](0013-streaming-tutor.md) | The tutor streams; it falls back only before the first token, and never waits | Accepted; amends 0007 and 0008 for interactive calls |
| [0014](0014-interactive-repairs-move-on.md) | An interactive JSON repair that's turned away moves to the next model, afresh | Accepted; amends 0013 |
| [0015](0015-voice-on-device-only.md) | Voice is on-device only: on-device Web Speech, local voices, no server fallback | Accepted |
| [0016](0016-workload-estimate.md) | A topic's workload is estimated from its pages, at 3 minutes a slide and 6 a page of text | Accepted |
| [0017](0017-planner-v1-rules.md) | Planner v1 rules: 50-minute blocks, two spaced blocks per topic, a final review, deadline order | Accepted |
| [0018](0018-study-methods-and-reason-text.md) | Study methods from a rules table; reason text and the feasibility report written by code, every number labelled | Accepted; builds on 0016 and 0017 |
| [0019](0019-planning-scope.md) | Planning scope: an assessment covers topic subtrees, ties break on course order, final reviews only for exams, tests and quizzes | Accepted; amends 0017 and 0018 |
| [0020](0020-review-fixes-spreading-and-overall-line.md) | Review fixes: a unit's blocks spread over its days, and the overall line never says "0 min" | Accepted; amends 0017 and 0018, notes 0019's example |
| [0021](0021-plan-versions-and-replanning.md) | Plan versions and re-planning: stored blocks, the next 24 h fixed, coalesced triggers, no churn, nightly | Accepted; amends 0017 |
| [0022](0022-moving-blocks-and-the-stored-plan-in-the-ui.md) | Moving blocks (pinned, six rules), history, derived status and server-side actions in GET /plan, the offline start fallback; review fixes | Accepted; amends 0021 |
| [0023](0023-review-fixes-done-blocks-drag-drops-past-days-qa-clock.md) | Done blocks at their measured time (planned_start/planned_end), drops from the pointerup on the window, no changes to past days, card names, sticky headers, one clock with FAKE_NOW (demo and e2e only), a version when the assessments change | Accepted; amends 0022 |
| [0024](0024-reminders-web-push-and-the-ics-feed.md) | Web Push (VAPID, pywebpush from the worker, one reminder per slot, per-device outcomes) and a private ICS feed (hashed token, slot UIDs) | Accepted |
| [0025](0025-practice-items-and-their-generation.md) | Practice items (flashcards and short answers), their cited sources, append-only reviews, and the generation job (topic subtree, learning kinds, Allow AI only; filtered; one per topic at a time) | Accepted |
| [0026](0026-fsrs-scheduling-and-the-review-queue.md) | FSRS scheduling (py-fsrs 6.3.3, fuzzing off, replayable snapshots, retention per review), reviews under a row lock, previews, the review queue with a local-day new allowance; tighter generation prompt | Accepted; amends 0025 |
| [0027](0027-topic-mastery-v1.md) | Topic mastery v1: recall, recency-weighted accuracy and the rating, recall weighted by its own sample (the task's formula failed monotonicity), computed on read with no stored table; review list and queue count fixes | Accepted; amends 0026 |
| [0028](0028-mastery-recall-a-week-ahead.md) | Mastery recall is FSRS recall a week ahead (R straight after any review read 1.0), no band while there isn't enough practice, review-generated properties with the exact Again exception | Accepted; amends 0027 |
| [0029](0029-the-practice-screen-and-ai-marking.md) | The practice screen and AI marking: the model judges each key point covered or not, code derives the verdict and suggested grade (never Easy), the student always presses the grade; reviews keep the marking; the review session, items, settings and Today screens | Accepted; amends 0025 and 0026 |
| [0030](0030-key-points-consistent-with-their-reference-answer.md) | Key points must be stated in their own reference answer: the prompt says so, and a batched consistency check after generation (the marking judgement) removes uncovered key points and drops an item left with none (`key_points_not_in_answer`) | Accepted; amends 0025 and 0029 |
| [0031](0031-mastery-in-the-plan-and-in-quiz-me.md) | Mastery in the plan (time `clamp(150 − mastery %, 70, 150)`, priority by strength, `low_mastery`, its text and methods; a `practice` re-plan 15 min after a review, coalesced) and in Quiz me (the band word only) | Accepted; amends 0017, 0018 and 0019 |
| [0032](0032-past-paper-parsing-approach.md) | Past-paper parsing (from spike S2): transcribe scanned or nearly empty pages, segment the whole paper in one call (98.1 %), qualify numbers in code, classify the whole paper with every topic (88.1 % chapter agreement); page-by-page segmentation only as the fallback | Accepted |
