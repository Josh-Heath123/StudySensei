# 0031: Mastery in the plan and in Quiz me

- **Date:** 2026-11-24
- **Status:** Accepted. Amends 0017 (time and priority within an assessment), 0018 (a new reason, its text and the
  methods table) and 0019 (each unit's inputs gain its mastery).

## Context

Phase 5 task 5: "Connect mastery to Quiz me and planner priority". Topic mastery (ADR 0027, 0028) estimates how well
the student knows a topic now, from their reviews, Quiz me answers and ratings. Until now the planner used only the
self-rated starting confidence, which never changes unless the student edits it, and Quiz me asked the same mix of
questions whatever the student's practice said. The rules that apply: the planner stays pure and has no AI; every word
of plan text comes from code; mastery is never presented as an exam prediction; every number shown is labelled
estimated with its sample size; nothing personal goes in a prompt (decision 0002).

## Decision

### Inputs

- `TopicInput.mastery: float | None`: the unit's mastery value when its status is `estimated` (3 attempts or more),
  else None. A `not_enough` value is never used: with fewer than 3 attempts the rating stands, as before.
- `load_plan_data` computes it per planning unit at `now`, over the same subtree as the unit (decision 0019), with one
  `mastery_by_topic` call per load (each planned module's `module_mastery`, which computes every topic over its subtree
  once), not one per unit. `TopicFacts` gains `mastery` and `mastery_attempts` for the text.
- `use_mastery=False` ignores it. Dev only: the preview CLI's `--no-mastery`, to compare.

### Time

One function, `strength_percent(topic)`, used by `required_minutes`:

- with mastery: `clamp(150 − m, 70, 150)` %, where m is the mastery as a whole percent, rounded half up (the figure the
  text shows, so the text and the time always agree). Mastery 0 gives 150 %, 0.5 gives 100 %, 0.8 or more gives 70 %;
- without: `CONFIDENCE_PERCENT` exactly as now (1: 150, 2: 125, 3 or unrated: 100, 4: 85, 5: 70).

The ends match the confidence table's, so a topic can't get more or less extra time from practice than from a rating.

### Priority within an assessment

Lower **strength** first, then course order, then id. Strength is the mastery, else the rating mapped `(c − 1) / 4`
(the mastery prior's own mapping, ADR 0027), else 0.5. With no mastery anywhere, the order is exactly today's
(confidence, then course order): `(c − 1) / 4` is increasing in c, and unrated maps to 0.5, the same place as 3. A
Hypothesis test checks the equality. Assessments still order by deadline, then weight.

### Reasons

- `low_mastery`: mastery below 0.5 (the weak band). It takes `low_confidence`'s place in the time-ordered assignment
  (after `no_estimate`, before `urgency`).
- `low_confidence` is used only when mastery is None.
- Migration 0028 adds `low_mastery` to the `plan_blocks.reason` check, with `practice` (below). Down turns stored
  `low_mastery` blocks into `low_confidence` ones (the nearest reason the old check allows) and deletes practice
  versions.

### Text

- `low_mastery`: "Your mastery is ≈ 34 % (estimated from 9 answers), so it gets 16 % more time." then the workload
  sentence.
- A unit with mastery above 0.5 (less time): its workload sentence ends "mastery ≈ 86 % (estimated from 12 answers), so
  30 % less time." The task asked for "(estimated)"; the sample size is added because every number shown carries it.
- "Answers" are the mastery's attempts (first reviews per local day and Quiz me answers). The words never say mark,
  score, pass or predict.
- The basis line: time is "adjusted for your mastery where it's estimated from your practice, else for your
  confidence."

### Methods

The first-block rows read mastery first: a unit's first block is `first_pass` when mastery < 0.5, `active_recall` when
≥ 0.5, and the confidence rule (1-2 or unrated: first pass; 3-5: active recall) when mastery is None. The table stays
four rows; later blocks are `practice` whatever the mastery.

### Re-planning after practice

- Each review queues a re-plan with trigger `practice` and `run_after = now + 15 min`, in the review's transaction.
- `enqueue_replan` gains `run_after` (default now). On conflict with the one queued re-plan it now updates
  `run_after = LEAST(queued, new)` instead of doing nothing: the queued job keeps its first trigger and its earliest
  time. So a sitting of reviews yields one re-plan 15 minutes after the first review, and a change that needs a re-plan
  now (an assessment edit) still gets it now.
- Migration 0028 adds `practice` to the `plan_versions.trigger` check. Its summary: "Your practice changed how strong
  some topics are." A re-plan that changes no block writes no version (ADR 0021), so a sitting that moves nothing
  leaves no trace in the history.

### Quiz me

- When the conversation has a topic whose mastery is `estimated`, the quiz prompt gets its band word only: "Their
  practice on this topic reads as weak. Ask mostly recall and definitions: …"; developing asks a mix; strong asks
  mostly application and comparison (`quiz.BAND_ASKS`). No number, no basis, nothing else about the student.
- Otherwise (no topic, or `not_enough`) the prompt is unchanged, byte for byte.
- The band is **derived study data, not personal data**: it says how practice on these sources went, as the sources
  themselves say what the course covers. It identifies no one and carries nothing the student wrote. Decision 0002
  stands.
- `grade` moved to `services/tutor/grading.py` (re-exported from `quiz.py`) so the mastery loader and the quiz service
  don't import each other.

## Alternatives

- **Scale time by mastery continuously without the rounding step.** The text would sometimes say "16 % more" for
  117 %. Rounding the shown percent first keeps them equal; the difference is at most 1 %.
- **Use the `not_enough` value too.** With 1-2 answers one lucky or unlucky card would swing the plan; the rating is the
  better guess until 3.
- **Re-plan inline after each review.** A sitting of 30 cards would write up to 30 versions and hold the plan lock on
  every grade. The 15-minute delay and coalescing give one.
- **Blend mastery and the rating in the priority key.** Mastery already includes the rating as its prior (ADR 0027),
  so blending would count it twice.
- **Send the mastery value to Quiz me.** A number invites the model to treat it as a score; the band is enough to pick
  the question mix.

## Consequences

- With no estimated mastery anywhere, plans are unchanged: every existing planner rule, property and scenario test
  passes untouched. Hypothesis properties also hold with random mastery added to the strategy (none failed).
- The scenario "the plan shifts toward weak topics" (equal workload of 5 h, mastery 0.3 and 0.9): 400 and 250 planned
  minutes (needed 360 and 210), and the weak unit's first block comes first.
- A student's ratings matter less as they practise: after 3 answers mastery decides a unit's time, order, reason and
  first method. The topic dialog still shows the rating, and the mastery's basis sentence says what it rests on.
- Phase 5's "done when: the plan shifts toward weak topics" is met in tests and the demo; the review-queue week of real
  use is still to come.
