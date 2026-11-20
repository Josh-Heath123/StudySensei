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
