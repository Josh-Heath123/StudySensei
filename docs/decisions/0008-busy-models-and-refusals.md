# 0008: Busy models and refusals move on; names under other keys

- **Date:** 2026-11-17
- **Status:** Accepted. Amends 0007 (bounded topic extraction).

## Context

After 0007, COS330's topic map rebuilt in 15 calls, but the same three materials failed again with "Stopped after 4
AI calls for this material without a usable answer". They were the Chapter 1, 5 and 7 study notes. From their
`ai_usage` rows (the new `detail` column) and `extract_topics` jobs:

| Material | Calls (in order) |
| --- | --- |
| Chapter 1 notes | Flash-Lite `invalid_json`, then 3 × Flash-Lite HTTP 503 |
| Chapter 5 notes | Groq HTTP 413 (13,390 tokens requested, limit 8,000 a minute), Flash-Lite 503, Flash-Lite `invalid_json`, Flash-Lite 503 |
| Chapter 7 notes | 4 × Flash-Lite HTTP 503 |

- **The 503s:** 9 of the 12 calls were Gemini's 503 "This model is currently experiencing high demand." Under 0007 a
  503 got one short retry on the same model and then raised `AIUnavailable`. The job waited and repeated, and
  every 503 counted toward the 4-call cap, so a busy afternoon used up the cap with nothing run. Chapter 7 never
  reached Groq.
- **The invalid replies:** both read `topics.0.name: Field required; topics.0.subtopics.0.name: Field required; …`
  for every topic and subtopic, with nothing else wrong. The model gave names under another key. Which key isn't
  recorded: `detail` holds field paths, not values. `title` is the likeliest, since the JSON Schema in the prompt has a
  `title` on every property. Both repairs hit a 503.
- **No content refusals:** no call came back with a safety or content filter or an empty reply.

## Decision

1. **A 503 is "busy", like a 429:**
   - It's logged as the new outcome `overloaded`.
   - It's retried once on the same model when the wait is short, then that model cools down and the next one is
     tried.
   - Other 5xx (500, 502, 504) still raise `AIUnavailable` without cascading.
2. **Turned away isn't spent:**
   - Requests turned away before running (429 and 503) don't count toward `TOPIC_MAX_CALLS` or the daily budget.
   - They have their own cap per run, `TOPIC_MAX_TURNED_AWAY` (20), so a long outage still ends with a plain message
     ("The AI providers were too busy… Use Retry topics later").
   - This amends 0007, which counted 429s toward the cap.
3. **Content refusals move on too:**
   - A reply whose `finish_reason` is `content_filter`, `SAFETY`, `PROHIBITED_CONTENT`, `BLOCKLIST`, `SPII` or
     `RECITATION`, or that is empty, is logged as the new outcome `refused`, with the reason in `detail`.
   - The next model is tried at once. The repair isn't spent and the model doesn't cool down (it's this content it
     won't answer).
   - A refusal counts toward the cap and the daily budget, because the request ran.
   - If every model refuses, `AIRefused` fails the job with each model's reason.
   - Not seen in the COS330 run. It's added because security notes are a likely trigger.
4. **Names under another key:**
   - A topic's or subtopic's name is also read from `title`, `topic`, `topic_name`, `subtopic`, `subtopic_name`,
     `heading` or `label` when `name` is missing or blank. This applies to the merge as well.
   - A node with no name under any of these is still rejected.
5. **Record the keys:** for a missing field, `detail` (and the repair prompt) now starts "an object had keys
   ['caption', 'pages'] but no 'name'". Only identifier-like keys are listed, never values, so no course text is
   stored.
6. Migration 0013 adds the two outcomes.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep counting 503s toward the 4-call cap | A provider's busy hour fails materials for good, with nothing run |
| No cap on turned-away requests | A long outage would reschedule a job forever |
| Store a snippet of invalid replies | It would put course text in `ai_usage`. Key names are enough to see the shape |
| Send a strict `json_schema` response format | Not supported the same way by every provider behind the OpenAI-compatible layer |

## Consequences

- Chapter 7's run would have reached Groq after two 503s.
- Chapters 1 and 5's replies would have validated on the first call (if the key was `title`). If it wasn't, the next
  failure's `detail` names the key.
- `ai_usage` can show `overloaded` rows (not counted toward the daily budget) and `refused` rows (counted).
- Groq's 8K tokens-a-minute limit still rules it out for parts over roughly 8K tokens. That's a 413 and moves on, as
  before.
