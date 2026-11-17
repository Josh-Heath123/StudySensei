# 0010: The merge's token ratio is 2.5 characters, and an oversized merge is reported, not cut

- **Date:** 2026-11-17
- **Status:** Accepted. Supersedes the 3.5 characters-a-token estimate in 0009 (decision 1).

## Context

0009 sized the compact merge request at 3.5 characters a token, from the full prompt's 4.6. On COS330 after PR #22
the compact request was refused by Groq three times with a 413 ("Limit 8000, Requested 9080–9103"), and Gemini
counted 9,031 input tokens. Measured from the dev database, built exactly as `merge_topics` builds it:

| | Characters |
| --- | --- |
| JSON instruction | 1,679 |
| System prompt | 1,573 |
| Header and 56 existing topics | 2,475 |
| 460 proposal lines | 20,403 (names 13,336, ids 3,200, page counts 2,775, indents 632, newlines 460) |
| Rest (the material tags, blank lines) | 1,076 |
| **Total, no descriptions** | **27,216** |

A single request to `groq/openai/gpt-oss-120b` with this input was refused: "Limit 8000, Requested 9072". That's 3.0
characters a token: ids, short names and page counts are token-dense.

## Decision

1. **The merge has its own ratio:**
   - `MERGE_CHARS_PER_TOKEN` = 2.5, with `estimate_merge_tokens`. With `TOPIC_MERGE_MAX_TOKENS` = 7,000 the
     budget is 17,500 characters, about 5,800 real tokens at the measured 3.0.
   - Nothing else used the old constant. Extraction is capped by `TOPIC_MAX_CHARS` in characters, for Gemini's
     long context.
2. **Over budget is reported, not cut:**
   - If the request with no descriptions is already over budget, `merge_messages` logs a warning with the
     character count, the budget and the number of proposals. It still sends every proposal, because the merge must
     be able to cite each one.
   - Groq refuses it (413, which uses no call cap), and Gemini takes it.
3. **The size test:**
   - It uses a COS330-sized synthetic module: 21 materials, 4 topics of 4 subtopics each, 56 existing topics, and
     names of COS330's average length (29 characters).
   - It checks the request against `TOPIC_MERGE_MAX_TOKENS` × 2.5 characters, counting the system prompt and the
     JSON instruction.
   - It's marked strict xfail. It renders 25,359 characters against 17,500, and it will fail loudly once the input
     fits, so the mark gets removed.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Drop proposals (or subtopics) until it fits | Explicitly ruled out: the merge must see and cite every proposal |
| Change the shared ratio for everything | Only the merge used it; prose prompts run near 4.6 |
| Keep 3.5 | Groq refuses requests the estimate says fit |

## Consequences

- COS330's merge still doesn't fit Groq. The names alone (13,336 characters) plus the fixed parts (6,803) are over
  17,500 characters. Gemini remains the only model that can take it.
- Making it fit needs a format change that keeps every proposal, a decision for later. Options include:
  - ids relative to their material (saves about 1.4K characters)
  - no page counts (about 2.8K)
  - merging in two halves
- Smaller modules still get descriptions while they fit.
