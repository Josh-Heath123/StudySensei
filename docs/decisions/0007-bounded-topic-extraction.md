# 0007: Bounded, lenient topic extraction: parts, call caps, pacing, no error cascades

- **Date:** 2026-11-18
- **Status:** Accepted. Amends 0006 (topic maps) and the client's failure handling from 0002.

## Context

The first real topic map ran on COS330 (21 materials). The tree was good, but 3 materials failed with "didn't come
out in the expected shape", and the run used far more quota than the ~22 calls it needed. From the dev database
(`ai_usage` for the day, and the `extract_topics` jobs):

| Purpose | Model | Outcomes |
| --- | --- | --- |
| topic_extraction | gemini-3.5-flash-lite | 8 ok, **66 invalid_json**, 28 error (~3 s) |
| topic_extraction | gemini-3.8-flash | 8 timeout (90 s each), 6 error |
| topic_extraction | groq openai/gpt-oss-120b | 10 ok, 10 error (~0.3 s), 5 rate_limited, 1 invalid_json |
| topic_merge | gemini-3.5-flash-lite | 1 ok, 5 invalid_json, 5 error |
| topic_merge | groq openai/gpt-oss-120b | 2 error |

- **Calls:** 142 for extraction and 13 for one merge, over 44 job attempts (12 jobs needed 2–3 attempts).
- **3.8 Flash:** all 18 of its daily budget went, 14 of them on failed topic calls.
- **The failed materials:** the Chapter 1, 5 and 7 study notes (24, 24 and 45 pages), each after 3 attempts.
- **Unknown causes:** `ai_usage` kept no reason for a failure, so why replies didn't validate isn't known. The
  proposals that did pass were well inside the limits (names ≤ 61 characters, descriptions ≤ 153, ≤ 8 subtopics),
  which points at shape details such as page ranges written as strings.
- **The multiplier was the cascade:**
  - an HTTP error or a repair on Flash-Lite moved the request on to 3.8 Flash (a 90 s timeout) and then to Groq,
    where whole decks exceed its 8K tokens a minute (likely the ~0.3 s errors)
  - when every model was out, the job was rescheduled without using an attempt, and the next run paid for the whole
    cascade again

## Decision

1. **Record why calls fail:**
   - `ai_usage.detail` (≤ 300 characters) holds the HTTP status and the provider's error message, or a summary of
     what didn't validate (field paths and rules, never values). Prompt and reply text are still never stored.
   - `ai_usage.job_id` ties each call to the job that made it.
   - A new outcome, `truncated`, marks a reply cut off at the output limit (migration 0012).
2. **Lenient output** (`schemas/topic_maps.py`): fix what can be fixed without guessing, reject only broken
   structure.
   - Names are clipped to 80 characters and descriptions to 300, at a word, with "…". A missing description is "".
   - Only the first 10 subtopics (15 in the merge) and the first 40 topics (25 in the merge) are kept.
   - A third level is folded into its parent: its pages (or the merge's sources) join the parent's.
   - Page numbers written as `3`, `"3"`, `"3-5"`, `"9–10"`, `"pp. 4, 6"` or `"12 to 13"` are all read.
   - A bare list instead of `{"topics": [...]}`, and a bare string instead of a topic, are accepted.
   - Still rejected, and so repaired once: not JSON, `topics` not a list, or a topic with no name.
3. **Cut-off replies and big materials:**
   - A reply with `finish_reason` `length` raises `AITruncated`. It isn't repaired, because asking again gives the
     same cut.
   - A material over `TOPIC_PART_PAGES` (40) pages is split into equal parts of about that size (for example 90 pages
     → 3 × 30), each extracted separately. Their topics are combined: the same name (ignoring case and punctuation)
     becomes one topic with the pages and subtopics joined.
   - A very long material gets bigger parts rather than more calls (at most `TOPIC_MAX_CALLS − 1` = 3 parts).
   - A cut-off part is split in half, budget permitting; a cut-off part under 4 pages fails with a plain message.
   - Finished parts are saved in the job's payload, so a retry or reschedule doesn't pay for them again.
4. **Bounded cost:**
   - At most `TOPIC_MAX_CALLS` (4) provider calls per material per run, and one repair, counting every fallback,
     retry and reschedule of that job (from `ai_usage.job_id`). The merge has the same cap.
   - A new run (Retry, or Build topic map) starts a fresh budget.
   - **Failure policy in the client, for every caller:** only "this model can't take it now" moves on to the next
     model: a 429, a timeout, a lost connection, or a 413 (the request is too large for that model's limits).
   - A 429 or 5xx is first retried once on the same model when its wait is short.
   - A 5xx that persists raises `AIUnavailable`, so the job waits and doesn't cascade.
   - Any other refusal (400, 401, 404…) raises `AIRequestFailed` with the provider's message, and the job fails at
     once.
   - Invalid output never moves to another model: its one repair goes to the same role from the top, and a further
     failure fails the run.
5. **Pacing:**
   - `AI_REQUESTS_PER_MINUTE` per model is the free-tier RPM less a margin: Flash-Lite 12 of 15, 3.8 Flash 4 of 5,
     Groq 25 of 30. A request waits its turn in a one-minute sliding window instead of collecting 429s.
   - The window lives in each process (the worker makes nearly all calls).
   - **Do 429s count toward the daily budget? No.**
     - A 429 is the provider refusing the request before it runs, and both Gemini and Groq describe their daily
       limits as requests made against the quota.
     - The diagnosis's 429s came back in ~0.2 s with no tokens, consistent with nothing being processed.
     - They still count toward the per-run call cap, since that bounds our own retries.
     - With pacing they should be rare, so the choice matters little either way.
     - Timeouts and 5xx do count toward the daily budget, because the provider may have run the request.
6. **Materials tab:**
   - each eligible material shows its topic state: analysed (with the number found), failed (with the reason), or
     waiting
   - a failed one has "Retry topics" (`POST /materials/{id}/topics/retry`, a new run)
   - `GET /modules/{id}/topic-map/materials` lists the states
7. **Merge prompt:**
   - New top-level topics follow the style of the module's existing top-level topics. The prompt lists them ("Ch1
     Overview", so "Ch4 Access Control").
   - A material that is its own chapter or lecture deck keeps its own top-level topic, rather than being folded into
     another (CH09 firewalls had ended up under intrusion detection).
8. **Clear AI topics:**
   - `DELETE /modules/{id}/ai-topics` deletes every topic still marked AI. Topics the student made or edited stay; one
     under an AI topic moves up to its nearest surviving ancestor, keeping the old tree's order.
   - Proposals are kept, so building again re-merges without re-analysing any material.
   - On the Topics tab it sits behind a confirm.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Strict schemas plus more repair attempts | Each repair is a call. Most rejections were fixable in code |
| Keep falling through on any error | That cascade caused the cost. A 400 or a persistent 5xx won't be fixed by a slower model |
| Pacing by counting `ai_usage` rows in the database | Works across processes, but adds a query per call. One worker makes nearly all calls |
| Counting 429s toward the daily budget | They're refused before running. Pacing keeps them rare |
| A larger call cap | 4 covers the parts of a 120-page material plus a spare; a new run is one click away |

## Consequences

- A typical module costs about one call per material plus one for the merge. In the worst case it's 4 per material and
  4 for the merge.
- A 400 or 401 now fails visibly with the provider's message instead of quietly using another provider. That includes
  a bad Gemini key in the tutor later: the student sees the reason.
- The next diagnosis can read `ai_usage.detail` instead of guessing.
- Over-long names show "…". The review UI (next task) lets the student rename them.
