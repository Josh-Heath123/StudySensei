# 0022: Moving blocks and the stored plan in the UI

- **Date:** 2026-11-21
- **Status:** Accepted. Amends 0021 (plan versions and re-planning).

## Context

Phase 4 task 5 puts the stored plan on screen: a week view where a student can see, start, skip and move blocks and
mark days unavailable, and Today's "Next up" with its reason. The web app must never reimplement a planning rule, so
whatever it needs to decide comes from the API. The post-merge review of #45 (live, temporary data since deleted) also
found four problems with re-planning, fixed first.

## Decision

### Review fixes (amend 0021)

1. **A linked session follows its block.** When `replan()` carries a block forward as a fixed copy, a session linked
   to the old row is pointed at the copy (`study_sessions.plan_block_id`) in the same transaction. Before this, ending
   a session started on version 2's block marked version 2's row done while version 3's copy stayed planned, stayed
   "next", and would later be marked missed.
2. **Only a planned block is marked done** when its session ends: one skipped meanwhile stays skipped.
3. **A block with an open linked session can't be skipped:** 409 "Its session is still open."
4. **The skip summary is true.** If the skipped block's assessment is shorter in the new report than in the previous
   version's: "You skipped Ch2 … (Fri 20 Nov, 19:00). There's no free time left to place it again before COS330 Exam,
   which is now 4 h 10 short." Otherwise "its time is placed again."
5. **Version 1's summary is always "Your first plan.",** whatever triggered it.
6. **No nightly retry loop.** `queue_nightly_replans` also skips a user whose re-plan job failed (gave up) since their
   most recent local 03:00.

### Moving a block

- **Pinned blocks** (`plan_blocks.pinned`, migration 0023): the student moved it. `replan()` carries every planned,
  not-yet-ended pinned block of the current version forward, beyond the 24 h window, while it stays valid by the rules
  for fixed blocks (inside free time, assessment upcoming, unit still covered). An invalid one is dropped and its
  unit's time is placed again. Pinned blocks go to `plan()` as fixed.
- **The rules** (`services/planning/moves.py`, pure; sentences in `explain.py`). The block keeps its length; the new
  start is on the 5-minute grid (the schema refuses anything else). In order:

  | Problem | When | Sentence |
  | --- | --- | --- |
  | `past` | it would start before now | "That time has passed." |
  | `after_deadline` | it would end after its assessment's due time | "That's after COS330 Exam (30 Nov, 09:00)." |
  | `review_window` | a final review would start before the 3 days before its assessment | "A final review stays in the 3 days before COS330 Exam." |
  | `outside_free_time` | not inside one stretch of free time on its local day (skipped slots count as busy) | "That's outside your study time on Tue 24 Nov." |
  | `too_close` | less than the 10-minute break from another block of the current version (fixed and pinned included) | "Leave 10 minutes between blocks." |
  | `over_cap` | the day's planned minutes, today's studied minutes if it's today, and this block exceed the cap | "Tue 24 Nov would go over your 3 h daily cap." |

  `review_window` wasn't in the brief. The Hypothesis property (re-plan with any accepted move pinned, then check
  every plan property) failed first on it: a review moved a week early broke "a final review in the last 3 days", and
  its text ("the last free time before …") would no longer be true.
- **`POST /plan/blocks/{id}/move {start}`,** under the user's lock: only a planned block of the current version that
  hasn't started and has no linked session (409 otherwise; 404 for another user's). A rule problem is a 422 with the
  sentence as `detail`. Otherwise it re-plans inline (trigger `move`): the block is pinned at its new time with its
  texts kept, and its old row stays on the old version. Summary: "You moved Ch2 … from Mon 23 Nov, 18:00 to Sat 28 Nov,
  10:00."

### What `GET /plan` returns (one code path, `stored.blocks_out`)

- **History:** the current version's blocks overlapping the range, plus done, skipped and missed blocks of any version
  overlapping it. Superseded planned rows of old versions are never returned.
- **Derived status:** a current planned block that ended with no linked session reads as missed, by the same predicate
  `mark_missed` uses (`replan.unattended`). Reading writes nothing; the next re-plan stores it.
- **Per block:** `linked_session_id`, `session_minutes` (the linked session's floored active minutes, for a done block;
  measured), `pinned`, and `actions` computed by the server:
  - `start`: planned in the current version, not ended, and no session open anywhere;
  - `skip`: planned in the current version, and no open linked session;
  - `move`: planned in the current version, not started, and no linked session.
- **`replan_pending`:** a re-plan job is queued or running. The page polls every 2 s while it's true, for up to 30 s.
- `GET /plan/next` returns the same block shape, with its actions.

### Starting a session from a block, offline-safe

The session engine sends `plan_block_id` with the start. If the server refuses the start with 404, 409 or 422 (the plan
changed while offline, say), the outbox sends it once more without the block, so the session is never lost. The
session screen then says, quietly, "Not linked to your plan: it changed."

## Alternatives considered

| Option | Why not |
| --- | --- |
| Moves only within the next 24 h (fixed anyway) | A student rearranges the week, not just tonight |
| Let `plan()` re-place a moved block | The student's choice would be undone by the next change |
| Compute actions in the web app | Duplicates the rules (statuses, sessions, the clock) and drifts; the server already knows |
| Store "missed" on read | A GET that writes surprises caches and retries; the next re-plan stores it anyway |
| Let a move put a review anywhere before the deadline | Breaks the planner's review guarantee and makes its reason text false |
| Drop the session when its block is refused offline | Loses measured study time; the block link is the less important half |

## Consequences

- Old versions' done, skipped and missed blocks show in the week view as history; superseded planned rows don't.
- A move is refused with one sentence, and the week view snaps the card back.
- Pinned blocks survive re-plans until they're invalid, so a student's arrangement holds while their time allows it.
- The web app decides nothing about the plan: it renders statuses and actions as the server sends them.
