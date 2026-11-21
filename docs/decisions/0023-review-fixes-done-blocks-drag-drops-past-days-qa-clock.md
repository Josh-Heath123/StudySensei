# 0023: Review fixes: done blocks at their measured time, drag drops, past days, QA clock

- **Date:** 2026-11-22
- **Status:** Accepted. Amends 0022 (moving blocks and the stored plan in the UI).

## Context

The post-merge review of #46 (live, with temporary data since deleted) found that a block studied early hid under the
block that re-used its slot, that a fast drag could be lost, that past days still offered changes, that card names
didn't say which day they were on, and that the QA screenshots never showed the normal states: the browser's clock
was fixed at the demo week while the API used the real clock, so every block read "Missed".

## Decision

1. **A done block is shown when it was studied.** `GET /plan` gives a done block its linked session's measured start
   and end as `start` and `end` (`minutes` is their length), and every block gains `planned_start` and `planned_end`
   (the plan's times). A range includes a done block whose session overlaps it, wherever its slot was. The popover
   says "Planned for Sat 21 Nov, 09:00". Before this, Sat 21 Nov's 09:00 block, started from Next up on Fri 20 Nov
   at 21:12 and ended, sat under the new 09:00 block the finish re-plan placed in its slot (two "09:00–09:50" rows).
2. **Drag drops come from the pointerup.** The drag lives in a ref, and the drop target is computed from the
   pointerup's own coordinates. While a drag lasts its moves and release are heard on the window: a fast flick's one
   pointermove and pointerup land on whatever is under the pointer, not the card, so card-level handlers (and
   capturing the pointer only after the first move) lost it. No pointer capture is needed, so clicks still open the
   popover.
3. **Past days can't be changed.** No day menu before today (in the user's timezone); today keeps it. Below 1024 px
   the agenda starts at today, and earlier days of the week fold under "Earlier this week", shown only when they have
   blocks.
4. **Card names say the day and the state:** "Sat 21 Nov, Ch1 Overview, 09:00 to 09:50, first pass", or "…, done,
   48 min (measured)", "…, skipped", "…, missed", "…, now". The same text is the card's hover title, since narrow grid
   columns cut its second row.
5. **The grid's day headers stick** under the floating nav (the card clips with `overflow: clip`, not `hidden`, which
   would make it the sticky header's scroll box).
6. **Move… opens on the block's own day and time.**
7. **One clock.** `app/core/clock.now()` replaces every `datetime.now(UTC)` in routers, services, the worker and the
   CLIs. A `FAKE_NOW` setting (ISO, with a timezone) freezes it, and is honoured only when the database's name ends
   in `_demo` or `_e2e`: anywhere else settings fail to load, so the API and worker refuse to start, with the reason.
   Queued jobs take `run_after` from the clock, not Postgres, so a worker on a fake clock in the past still runs them.
   `npm run screenshots` runs the API, worker and seed with `FAKE_NOW` at the demo's now (Thu 19 Nov 2026, 18:20) and
   fixes the browser to the same instant. The demo seed makes three days of plan history through the real re-plan
   code: version 1 on Monday morning, Monday's block done with a linked session, Tuesday's skipped, Wednesday's left to
   be marked missed by the nightly re-plan at 03:00, which also keeps tonight's block, in progress at the demo's now.
8. **A cascade still writes a version.** Deleting an assessment cascades its blocks out of the current version, so the
   remaining blocks can equal the new plan's and the header kept the old summary. A re-plan now also writes a version
   when the new report covers different assessments.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep a done block at its planned slot, and offset the re-used block beside it | Two cards in one slot; it misstates when the studying happened |
| Capture the pointer on pointerdown | It retargets the click, so a tap no longer opened the popover (found in #46) |
| A fake clock that advances from `FAKE_NOW` | Screens would drift between shots; the browser's clock is fixed, so the API's is too |
| Allow `FAKE_NOW` anywhere, with a warning | A real plan on a fake day writes wrong versions and marks the wrong blocks missed |
| Compare reports' text, not their assessments | Text changes with every minute of free time; the assessments covered are what makes the header stale |

## Consequences

- The week view shows the studying where it happened; the planned slot is in the popover and the API.
- The README screenshots move from Monday morning to Thursday evening (regenerated when Phase 4's gate closes).
- Code that needs the time asks `clock.now()`; a test can freeze it by setting `FAKE_NOW` on an `_e2e` database.
