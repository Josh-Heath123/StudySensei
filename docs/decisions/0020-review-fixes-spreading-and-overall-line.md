# 0020: Review fixes: spreading a unit's blocks and the overall line

- **Date:** 2026-11-21
- **Status:** Accepted. Amends 0017 (planner v1 rules, rule 9.3) and 0018 (the overall line); notes an error in
  0019's example.

## Context

The post-merge review of #44 on COS330 (temporary data, since deleted) confirmed what #44 promised, and found:

- **Stacking.** A test covering only Ch5 (one unit, 6 blocks), with weekday evenings 18:00–21:00, got 18:00, 19:00 and
  20:00 on its first evening and one block on each of the next three. Pass 3 tried only each gap's first start (always
  straight after a block). And its "next to" test looked at the nearest block on the day however far away, so once
  every day had the unit, every spot counted as "next to" and the fallback was plain earliest. #44 made single-unit
  assessments common.
- **The overall line** read "You need 0 min before 26 Nov and have 21 h." with nothing to do. When an assessment was
  short although the total time covered the total need (the time was in the wrong place), the line didn't say which
  one.
- **Under a minute** of measured study read "0 min studied so far (measured, 1 session)".
- **The topic dialog** rounded a chapter's own estimate to the nearest half hour ("≈ 2.5 h") right above the
  planner's figure with its subtopics ("≈ 4 h 20").

## Decision

1. **Pass 3 spreads a unit** (amends ADR 0017 rule 9.3). The earliest spot on a day the unit doesn't have yet still
   comes first. When every day with room already has the unit, choose:
   1. the day with the fewest of the unit's blocks;
   2. then a spot not **directly** next to its own block, meaning only the 10-minute break lies between them (a
      neighbouring day's block counts across midnight);
   3. then the earliest.

   Each gap is tried at its earliest and its latest start. These preferences apply once the unit has blocks on two
   or more days. With its blocks on one day only (no other day had room), there is nothing to spread, and the
   earliest spot is kept. Without that condition, `test_the_daily_cap_and_the_break_between_blocks` (a single free
   day) would move its second block from 10:00 to the end of the day. The spec kept every existing test unchanged.
2. **The overall line** (amends ADR 0018):
   - with 0 required minutes: "Nothing more is needed before 26 Nov; you have 21 h free." (the assessment lines say
     why);
   - when the status is short but required ≤ free: "You need 21 h 45 before 7 Dec and have 36 h, but COS330 Exam
     (30 Nov) is 3 h 20 short." With several short assessments: "…, but 2 assessments are short.";
   - otherwise unchanged: "You need 14 h before 3 Dec and have 9 h."
3. **Under a minute:** a unit with sessions whose floored minutes are 0 reads "under 1 min studied so far (measured,
   1 session)".
4. **One format for estimates in the UI:** every topic estimate, in the dialog and the topic rows, uses the planner's
   format ("≈ 2 h 15"), and `aboutDuration` is removed. The Settings → Study time weekly summaries ("12.5 h") keep
   their own format; they describe time available, not an estimate of a topic.
5. **A note on ADR 0019:** section 1, item 7's example "≈ 7 h 15 estimated from 72 slides and 34 pages of text"
   should read **≈ 7 h** (72 × 3 + 34 × 6 = 420 minutes, ADR 0016). The code was always right; the docstring, a
   comment and two test fixtures that copied the example are corrected. ADR 0019 itself is not edited.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Treat the unit's nearest block anywhere on the day as "next to" | That's the bug: every spot qualifies once each day has the unit |
| Spread by a minimum gap in minutes (e.g. 2 h) | Another number to tune; "only the break between them" is what back-to-back means to a student |
| Apply the preferences even with one free day | Changes a settled rule test, and moving a block to the end of a single free day gains nothing |
| "You need 0 min…" kept for consistency | Reads as an error; the assessment lines already explain why nothing is needed |

## Consequences

- The single-unit case now spreads 2, 2, 1, 1 over four evenings (it was 3, 1, 1, 1), and a day's second block sits
  at the far end of the evening.
- Every ADR 0017 rule, scenario, property and timing test is unchanged and still passes.
