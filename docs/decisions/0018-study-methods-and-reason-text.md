# 0018: Study methods and reason text

- **Date:** 2026-11-20
- **Status:** Accepted. Builds on 0016 (workload estimate) and 0017 (planner v1 rules).

## Context

Planner v1 (ADR 0017) gives each block a machine-readable reason and the plan a list of shortfalls. A student needs
more than that: what to do in the block, why it's there, and whether the plan covers what each assessment needs. The
rules say AI never changes the plan, and AI providers are free tiers that must not see personal data, so the words
have to come from code. PRODUCT.md had planned for AI to write the explanation of each block's method. For v1, code
writes all of it.

The planner's inputs also have to come from the database for the first time (the preview endpoint and the CLI), so
this record fixes what counts.

## Decision

### Inputs (`services/planning/inputs.py`)

1. **Window:** `days` local dates from today (1 to 62, default 28, as `GET /availability`), in `users.timezone`.
   Free time is `availability.expand()` over those dates (exceptions over rules), with the user's daily cap.
2. **Assessments:** status `upcoming` (not `completed` or `cancelled`), due after now **and by the end of the
   window**. One due later is listed as "after these N days: not planned yet", because the window has no free time
   for it and its review; saying it was short would be false.
3. **Topics:** those the assessments cover, with workload (the student's figure, else the ADR 0016 estimate, else
   none) and starting confidence.
4. **Studied minutes per topic** (measured): the sum of `study_sessions.active_seconds` for sessions with that
   `topic_id`, floored to whole minutes, with the number of sessions. **A session on a subtopic counts for that
   subtopic only**, not its parent: the parent's workload is its own linked pages, so counting a child's time there
   would subtract time spent on pages the parent's figure never included.

### Study methods (`services/planning/methods.py`)

A rules table kept as data, one row per rule, checked in order; the first match wins and the last row matches
everything.

| # | When | Method | What the student does |
| - | ---- | ------ | --------------------- |
| 1 | A final review | `mixed_review` | Mixed recall across the assessment's topics, then fix the gaps. |
| 2 | A topic's first block, confidence 1–2 or not rated | `first_pass` | Read the linked pages and make short notes. |
| 3 | A topic's first block, confidence 3–5 | `active_recall` | Write what you remember, then check the pages. |
| 4 | Spacing and later blocks | `practice` | Quiz yourself first (Quiz me), then re-read what you missed. |

"First" is first in time in this plan. Not rated counts as unsure (row 2): reading before recall is the safer start.

### Reason text (`services/planning/explain.py`)

One or two short sentences per block from its reason and the facts behind it:

| Reason | Text |
| ------ | ---- |
| `urgency` | "COS330 Test 2 is in 6 days (30 % of the module)." then the workload sentence |
| `low_confidence` | "You rated this 2 of 5, so it gets 25 % more time." then the workload sentence |
| `no_estimate` | "No slides or pages are linked yet, so it gets two blocks by default. Set your own time in the topic." |
| `workload` | "≈ 40 min estimated from 13 slides; 15 min studied so far (measured, 1 session)." |
| `spacing` | "A second day on this topic helps it stick." |
| `final_review` | "The last free time before COS330 Test 2: a mixed review of its topics." |

- **Every minute figure carries its basis:** "estimated from N slides / pages of text", "by your own figure", or
  "measured, N sessions" ("not studied yet (measured: no sessions)" at zero).
- **Nothing the inputs don't contain:** no weight means no "(N % of the module)"; days count from the block's local
  date to the deadline's ("today", "tomorrow", "in N days").
- Durations read "40 min", "3 h", "4 h 10".

### Feasibility (`services/planning/feasibility.py`, pure)

From the `Plan` and its `PlanInput`:

- **Per topic:** required minutes (ADR 0017), planned minutes (its study blocks), short = `max(0, required − planned)`.
  Over-planning one topic never covers another.
- **Per assessment:** the sums over the topics planned for it, its review minutes, free minutes from now to its
  deadline (split at local midnight, each day at most the cap) and booked minutes (every block, any assessment's,
  that starts before the deadline).
- **Status:** `short` if anything is short; `tight` if covered with under 15 % of the free time left over
  (`free − booked < 15 % × free`); otherwise `fits`. Overall uses the same rule over everything to the last deadline.
- **Shortfalls in words:** `not_enough_time` ("needs 4 h 10, 3 h planned: 1 h 10 short"), `not_spaced`,
  `no_estimate`, `no_review_time`, `no_topics` ("covers no topics yet: add them in its Assessments tab").
- **The overall line:** "You need 14 h before 3 Dec and have 9 h." (needed = required minutes; have = free minutes),
  with one line saying both are estimated or taken from the student's study time.
- **Levers** when anything is short or tight, as plain options: add study time; raise the daily cap (only if the cap
  cuts some day's free time); narrow each short assessment's topics.
- **Properties (Hypothesis):** per topic, planned + short = required whenever short > 0, and a `not_enough_time`
  shortfall exactly then; totals are the sums of their parts; the status agrees with the numbers; free time never
  falls with a later deadline.

### Preview

`GET /plan/preview?days=` and `python -m app.planning.preview` compute all of this on request. Nothing is stored
(`plan_blocks` is task 4).

## Alternatives considered

| Option | Why not (for v1) |
| ------ | ---------------- |
| AI writes each block's explanation (PRODUCT.md's earlier plan) | A free-tier call per block, latency on every re-plan, and a risk of numbers the inputs don't hold; a template states the facts exactly |
| A method score (weights per factor) | Hard to explain in a sentence; four rows cover the cases v1 knows about |
| A subtopic's sessions also count for its parent | The parent's workload counts only its own pages, so it would subtract time spent elsewhere |
| Plan assessments past the window with the time inside it | Every one would read "short" and "no review time" for lack of looking; listing them as later is honest |
| Status from shortfalls (any shortfall = short) | `no_estimate` and `not_spaced` aren't about time; status follows the minutes, shortfalls are listed beside it |

## Consequences

- Every word on a block is reproducible from its inputs and testable; changing a phrase is a code change with a test.
- PRODUCT.md's "Study method per block" row now says code writes the text, with no AI in v1. An AI rewording could come
  later only if it is given the computed sentence and its numbers, and validated.
- Methods ignore mastery and past papers until Phases 5–6; when those arrive, a new record adds rows (for example,
  past-paper practice before an exam).
- Over-planning a nearly finished topic (two 50-minute blocks for a 5-minute need, ADR 0017) shows up as planned far
  above needed; the report doesn't call that short.
- A parent topic whose pages are all linked to its subtopics has a small or no estimate; covering the subtopics in the
  assessment gives a truer figure.
