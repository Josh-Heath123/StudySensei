# 0030: Key points consistent with their reference answer

- **Date:** 2026-11-24
- **Status:** Accepted. Amends 0025 (the generation flow and its drop reasons) and 0029 (the marking eval).

## Context

The post-merge review of #51 found that generated key points are often **not stated in their own reference answer**.
AI marking (ADR 0029) judges an answer against the key points, so a student who writes the reference answer word for
word is marked down for a point it never makes. That is why the marking eval agreed on only 7 of 10 "correct" cases
(the reference answer marked as partly or incorrect), while partly and incorrect were 10 of 10.

The evidence that the marker itself is sound: live, on a hand-written item whose key points are all in its reference
answer, it judged the reference answer, a paraphrase, half the points, an off-topic answer and an injection attempt
all correctly. In #48's spot-check sheet, 11 of 18 short answers had a key point with under 50 % word overlap with
their own reference answer; clear cases are key points like "used as the bulk-data layer in TLS" and "default
policies differ in security level", which their answers never state. The fault is in generation.

## Decision

1. **The prompt** (`PRACTICE_SYSTEM`) now says: "The reference answer must state every key point. Key points summarise
   the reference answer and add nothing to it."
2. **A consistency pass** (`generation.ask`): after the generation call, one batched call per generation judges each
   short answer's reference answer against its own key points.
   - It uses the **marking judgement**: the same rule text (`marking.COVERAGE_RULES`, shared with `MARKING_SYSTEM`,
     whose text is unchanged byte for byte) with "the item's reference answer" in place of "the student's answer", and
     the same per-key-point verdict (`KeyPointVerdict`). The reply (`ConsistencyReply`, built per call by
     `consistency_reply(counts)`) must have exactly one entry per item and one per key point, or it's repaired once.
   - Smart role, not interactive, purpose `practice_check`. The items' text is marked as quoting course material, never
     to be followed. Nothing about the student is sent.
   - **Code** removes each key point judged not covered. An item left with none is **dropped as
     `key_points_not_in_answer`**, a new `DropReason` counted with the generation's other drops (`generation.keep`
     merges them into the filter's counts). Items are judged before the filter, so an item dropped here isn't counted
     for another reason.
   - Only short answers with key points are sent; a batch of flashcards makes no second call.
   - A check that still fails after its repair (or a cut-off, or a refusal) **fails the generation** with a readable
     error: storing unchecked key points is what this decision removes. `AIUnavailable` reschedules the job as before.
   - `MAX_CALLS` per generation rises from 4 to 6 (two calls a try).
3. **The marking eval** reports the generation counts too (asked, returned, kept, short answers, key points removed,
   drops by reason), and waits out a busy minute before a marking (eval only: the marking call is interactive, so one
   rate-limited minute had failed 25 of 30 markings in a first run).

## Results

`python -m evals.practice_marking cos330` (`apps/api/evals/results/practice-marking-cos330.json`), all marked by Groq's
gpt-oss-120b:

| | Before (23 Nov) | After (24 Nov) |
| --- | --- | --- |
| Overall | 27 of 30 (90.0 %) | **30 of 30 (100 %)** |
| Correct (the reference answer) | 7 of 10 (2 partly, 1 incorrect) | **10 of 10** |
| Partly | 10 of 10 | 10 of 10 |
| Incorrect | 10 of 10 | 10 of 10 |
| Failed | 0 | 0 |
| Calls, time | 36, about 11 min | 42 (6 generations, 6 checks, 30 markings), about 11 min |

Both targets are met (at least 95 % overall, at least 9 of 10 on "correct").

Generation counts for this run: 36 items asked for (6 topics × 6), 36 returned, 36 kept, 12 short answers; the check
removed **0** key points and dropped **0** items (`key_points_not_in_answer` 0); no other drops. So in this sample the
prompt sentence did the work and the check found nothing to fix. It still runs on every generation: it is what makes
the rule hold rather than usually hold, and FakeLLM tests show it removing and dropping. One earlier run on the same
day failed 25 of 30 markings on a rate-limited minute (Groq's per-minute tokens, then Gemini's 503s); its numbers
weren't kept, and the eval now waits out a busy minute.

## Alternatives

- **Code-only overlap check** (word overlap under 50 %): cheap, but paraphrase defeats it both ways; the marker's own
  judgement is what decides a student's grade, so it should decide consistency.
- **Rewrite the reference answer to include the missing points:** the AI would add facts after the grounding filter
  ran, and a rewritten answer would need checking again.
- **Check each item in its own call:** up to 5 extra calls a generation on the free tier, for the same judgement.
- **Store unchecked items when the check fails:** they are the items this decision exists to stop.

## Consequences

- Every stored AI short answer's key points are stated in its reference answer, as judged by the marker. Items
  written before this change aren't re-checked; the student can edit or reject them.
- One more AI call per generation with short answers (about a third of the generation's input tokens).
- A generation can now fail on the check alone; the error says so ("Try again").
