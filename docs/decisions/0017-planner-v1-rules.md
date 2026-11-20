# 0017: Planner v1 rules

- **Date:** 2026-11-20
- **Status:** Accepted.

## Context

Phase 4 needs a planner that decides what to study and when, and can explain each block. Its inputs exist after task 1:
free time per local day (`availability.expand`, in UTC), the daily cap and timezone, assessments with their topics, and
each topic's workload (the student's figure or the estimate of decision 0016) and starting confidence. Sessions give the
minutes already studied per topic.

The planner has to be predictable and testable before anything stores or shows its output, so it's a pure function
(`services/planning/planner.py`, `plan(PlanInput) -> Plan`) with no database, no clock and no AI. The rules below are
deliberately simple: a student should be able to guess why a block is where it is.

## Decision

### Blocks

1. **50 minutes, matching the timer,** with the timer's **10-minute break** between neighbouring blocks (also across
   local midnight).
2. **A 25-minute block only where no 50 fits:** in a stretch of free time shorter than 50 minutes (the end of a window,
   or the time left before a deadline). Never to squeeze under the daily cap.
3. **A 5-minute grid.** Free time is rounded inward to it, and `now` is rounded up.
4. **Never** in the past, outside the free intervals, past the daily cap (counted per local day in the user's
   timezone, by the day the block starts; free time is split at local midnight), or after the deadline of the
   assessment the block is for.

### What each topic needs

5. **In scope:** a topic covered by an upcoming assessment (due after now) with work left. A topic in several
   assessments is planned for the soonest one; the later ones still review it.
6. **Required minutes** = `max(0, workload − measured minutes)`, scaled by starting confidence and rounded up to 5:

   | Confidence | 1     | 2     | 3 or not rated | 4     | 5     |
   | ---------- | ----- | ----- | -------------- | ----- | ----- |
   | Time       | +50 % | +25 % | +0 %           | −15 % | −30 % |

7. **No workload figure:** two blocks (100 minutes, less what's been studied), and a `no_estimate` shortfall.

### Order and placement

8. **Priority:** sooner deadline, then higher weight (none counts as 0), then lower confidence (none counts as 3), then
   the assessment's and the topic's ids. Input order never matters.
9. **Three passes,** sooner deadlines first in each:
   1. **Final review:** one block covering the assessment's topics in the 72 hours before it, **as late as fits**,
      placed before any study so study never crowds it out. An assessment with no topics gets none (`no_topics`).
   2. **Spacing:** every in-scope topic gets **two blocks on different local days**, each **as early as fits**. A later
      assessment's topics look first at the days after the previous deadline, and fall back to any day; that leaves
      the earlier days to the earlier assessment's remaining workload.
   3. **Workload:** the rest of each topic's required minutes, one block per topic per round so topics interleave. Each
      block goes on the earliest day the topic doesn't have yet; failing that, at the earliest spot that isn't directly
      next to the topic's own block; failing that, the earliest spot.
10. **Two blocks is a minimum,** even if a topic needs less time: spacing is the point.

### Output

11. **Blocks:** start, end, module, assessment, topic (none for a review), kind (`study` or `review`) and one
    machine-readable reason, assigned in time order: `final_review`; `spacing` (a topic's first block on a second
    day); `no_estimate`; `low_confidence` (rated 1 or 2); `urgency` (due within 7 days of the block); `workload`.
    Task 3 turns these into text.
12. **Shortfalls**, for task 3's feasibility report: `not_enough_time` (with required and planned minutes),
    `not_spaced` (fewer than two days), `no_estimate`, `no_review_time` and `no_topics`.

### Properties (Hypothesis, `tests/planning/`)

No overlapping blocks (with the break); every block inside free time; per local day, minutes ≤ the cap; nothing in the
past or after its deadline; two blocks on different days per topic whenever time allows (defined below); a final
review whenever the 3 days before an assessment have room for one around the other reviews; the same plan for the same
input in any order; a `not_enough_time` shortfall exactly when a topic gets fewer minutes than it needs.

"Time allows" for spacing uses Hall's condition: over the whole local days between today and the deadline's day, after
the reviews, the sum of min(50-minute blocks that fit in the day, topics due by then) is at least twice the number of
topics due by then. A day can hold only one of a topic's two blocks, so with less than that no plan could space them
all.

## Alternatives considered

| Option                                                                      | Why not (for v1)                                                                                                         |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| A solver (integer programming or constraint programming)                    | Better packing, but a dependency, slower, and hard to explain in one line; the greedy passes meet every property         |
| A priority score, importance × (1 − mastery) × urgency (the earlier sketch) | Needs mastery (Phase 5) and past-paper importance (Phase 6); a single score also hides why one topic beat another        |
| A fixed grid of slots (on the hour)                                         | Simpler, but wastes windows that start at odd times and can't fit a 25-minute block before a deadline                    |
| Study as late as possible                                                   | Leaves no slack for a missed block; early placement plus re-planning (task 4) keeps the time before a deadline free      |
| Keep a topic's blocks for its later assessments too                         | Studies the same pages twice before the second exam; the final review covers it, and mastery (Phase 5) can add practice |

## Consequences

- The plan is deterministic and fast (2 modules × 30 topics × 30 days in about 5 ms locally; the test allows 200 ms).
- Minutes already studied today don't count against today's cap yet; the caller can lower the cap or the free time.
- Two minimum blocks can over-plan a nearly finished topic (up to 100 minutes for one that needs 5). The shortfalls
  and the feasibility report make the trade-off visible.
- Mastery, past-paper importance and study methods are not inputs yet. When they are (Phases 5–6), a new ADR amends
  the priority and the required minutes; the properties stay.
- Keeping the next 24 hours fixed when re-planning is task 4's job (it stores `plan_blocks` and passes the fixed blocks
  in as busy time).
