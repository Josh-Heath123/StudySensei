# 0013: The tutor streams; it falls back only before the first token, and never waits

- **Date:** 2026-11-19
- **Status:** Accepted. Amends 0007 and 0008 for interactive calls; background jobs are unchanged.

## Context

The tutor (Phase 3) answers while a study session runs. The ROADMAP asks for a first token in under 2 s. The client
built for topic maps (decisions 0007, 0008) waits for a whole reply. On a 429 or 5xx it retries the same model after
its Retry-After or a 2–4 s backoff, then moves on. That's right for a background job and wrong for a student waiting
on a sentence.

Streaming adds a case `complete_text` never had: a model can fail after part of the answer has been shown.

The interactive rule was decided on 17 Nov: interactive calls don't wait.

## Decision

1. **Streaming:** `LLMClient.stream_text` uses the same OpenAI-compatible adapter with `stream: true` and
   `stream_options.include_usage`, parsing SSE with httpx. It yields answer text, then one `StreamDone` (model,
   finish reason, tokens, timings). The rest is shared with `complete_text`: routes, daily budgets, pacing, timeouts,
   effort levels, and one `ai_usage` row per attempt (no text; output tokens recorded at the end).
2. **Fallback only before the first token:**
   - A 429, 503, 413, timeout, lost connection, error event or refusal before any answer text moves on to the next
     model.
   - After the first token, any failure ends the stream with `AIStreamFailed`. The tutor keeps the text so far as a
     `failed` message and sends an `error` event.
   - Two models' text is never spliced into one answer.
3. **The first token is the first answer token.** Reasoning deltas (gpt-oss on Groq) are never streamed to the client
   and don't count. A model that thinks, then drops the connection before answering, still falls back.
4. **Interactive calls never wait:**
   - A 429 or 503 moves straight on to the next model, with no retry and no backoff.
   - Any other 5xx raises `AIUnavailable` at once.
   - A 401 (or 400, 404) still fails visibly as `AIRequestFailed` and isn't passed on.
   - `interactive=False` keeps 0007's behaviour (one short retry on the same model), and `complete_text` is
     unchanged. Both paths share one rule, `_after_failure`.
5. **Length is not an error:** `finish_reason` "length" ends the stream normally and marks the answer `truncated`.
   A refusal part-way through ends it as a failure.
6. **Stopping:**
   - When the reader stops (the student closes the tutor or the page), the provider's HTTP stream is closed.
   - The attempt is logged with a new `ai_usage` outcome, `stopped`, which counts toward the daily quota (the request
     ran).
   - The partial answer is stored as `stopped`. Both writes run in a shielded cancel scope, because FastAPI cancels
     the endpoint's generator on disconnect.
7. **SSE to the browser:** FastAPI's own `EventSourceResponse`, with typed events `sources`, `delta`, `done` and
   `error`. A dependency checks the conversation and runs retrieval before the stream opens, so another user's
   conversation is a plain 404 rather than an error inside a 200 stream.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Retry or fall back after the first token, appending the next model's text | Splices two models' answers; citations and style don't line up |
| Restart the whole answer on the next model, clearing what was shown | Confusing mid-sentence, and doubles the calls; the student can ask again |
| Keep 0007's waits for the tutor | A 2–4 s backoff alone breaks the 2 s first-token target |
| Count thinking deltas as the first token | Hides the wait the student actually sees |
| Hand-rolled `StreamingResponse` | FastAPI 0.162 has SSE built in, with keep-alives, OpenAPI item schemas and cancellation through the request's exit stack |

## Consequences

- **Real check (COS330, dry run, 19 Nov 2026):**
  - Five eval questions, each with its topic, were answered by `groq/openai/gpt-oss-120b`.
  - First tokens came at 703–843 ms, including 46–77 ms of retrieval.
  - Every answer cited at least one acceptable page.
  - Loading the embedding model (about 850 ms) happens once per API process, at the first search.
- **gpt-oss often cites in full-width brackets (`【S1】`):** it did in 3 of 5 answers, even when asked for `[S1]`.
  Citations are parsed in both forms and the text is stored as written, so the tutor panel (task 3) must render
  both.
- **A busy primary is skipped quickly:** a 429 or 503 on Groq goes to Flash-Lite in one round trip. Each skip still
  sets the usual cooldown, so the next question doesn't knock on the same busy model.
- **Mid-answer failures are visible:** the student sees a partial answer marked as failed and can ask again. That
  costs one more call, but nothing is silently mixed.
