# 0021: Plan versions and re-planning

- **Date:** 2026-11-21
- **Status:** Accepted. Amends 0017 (planner v1 rules): fixed blocks, and minutes studied today count against today's
  cap.

## Context

Until now a plan was computed on request (`GET /plan/preview`) and thrown away. Phase 4 task 4 needs a plan that
stays put: blocks a student can start, skip and finish, a history of what was done, and a plan that adjusts by itself
when things change, without reshuffling the evening the student is about to sit down to. The roadmap's check is "skip
a block and check the plan adjusts and explains why".

## Decision

### Data (migration 0022)

- **`plan_versions`:** `number` (from 1, `UNIQUE (user_id, number)`), `trigger`, `summary` (one code-written
  sentence), `generated_at`, `checked_at`, `days`, and `report` (JSONB: the feasibility report exactly as
  `GET /plan/preview` returns it). `UNIQUE (id, user_id)`.
- **`plan_blocks`:** a version's blocks, with start and end (UTC), module, assessment, topic (null for a review),
  kind, reason, method, `reason_text` and `method_text` as generated for that version, `status` (`planned`, `done`,
  `skipped`, `missed`), `status_changed_at`, and `fixed`. `UNIQUE (id, user_id)`; an index on `(user_id, start_at)`.
  Composite FKs on `(…, user_id)` to `plan_versions`, `modules`, `assessments` and `topics`. Deleting a module,
  assessment or topic deletes its blocks.
- **`study_sessions (plan_block_id, user_id) → plan_blocks (id, user_id)`, `ON DELETE SET NULL (plan_block_id)`**
  (Postgres 15+), so `user_id` is kept.
- **`jobs`:** a partial unique index on `(user_id) WHERE kind = 'replan' AND status = 'queued'`.
- **Nothing is pruned.** Old versions and their blocks are the history behind PRODUCT.md's consistency metric.

### Statuses

| Status | Set when |
| --- | --- |
| `planned` | the block is written |
| `done` | a session linked to it (`plan_block_id`) first gets an end; `status_changed_at` is that end |
| `skipped` | the student skips it (`POST /plan/blocks/{id}/skip`) |
| `missed` | a re-plan finds it ended (`end_at ≤ now`) with no linked session |

Done, skipped and missed blocks stay on the version they belong to.

### The planner (amends 0017)

- `PlanInput.fixed`: blocks returned unchanged and treated as busy. Nothing overlaps them, the 10-minute break applies
  around them, and they count against their local day's cap. A fixed study block is time already scheduled for its
  unit, and its day counts as one of the unit's days (for spacing and ADR 0020's spreading). A fixed review is its
  assessment's final review.
- `PlanInput.studied_on`: measured minutes per local date. Today's (sessions that started since local midnight) count
  against today's cap. This closes ADR 0017's known gap.

### `replan(session, *, user_id, now, trigger, detail)`

1. **Lock:** `pg_advisory_xact_lock(hashtextextended(user_id::text, 0))`, so two re-plans for one user never
   interleave and version numbers stay unique and gap-free.
2. **Missed:** the current version's past planned blocks with no linked session. A block whose session is still open
   stays planned.
3. **Fixed (the next 24 h):** the current version's planned blocks that haven't ended and start within 24 h (one in
   progress included), unless it was skipped, it's no longer inside free time, its assessment is no longer upcoming,
   or its topic is no longer in any upcoming assessment's units. A fixed block keeps the texts and method it was
   generated with.
4. **Skipped time stays free:** the times of skipped blocks that haven't ended (any version) are taken out of the
   free time, so the unit's time is placed again elsewhere, not back in the slot the student just declined.
5. **Plan** with `load_plan_data` (28 days), the fixed blocks and today's minutes, through `preview.build`. This is
   the preview's own code path, not a copy.
6. **No churn:** compare the new blocks (start, end, module, assessment, topic, kind, reason, method and both texts;
   not the `fixed` flag) with the current version's planned blocks that haven't ended. If they're equal, write no
   version: refresh the current version's report and `checked_at`. Blocks are compared, not the report, because free
   minutes change as time passes. Otherwise write version n + 1 with all its blocks.
7. With no version yet, the first run writes version 1 with the trigger it was given. `GET /plan` with no version
   runs `replan(trigger initial)`.

### Triggers

| Trigger | When | How | Summary |
| --- | --- | --- | --- |
| `initial` | `GET /plan` with no version | inline | "Your first plan." |
| `skip` | `POST /plan/blocks/{id}/skip` | inline | "You skipped Ch2 … (Tue 24 Nov, 18:00): its time is placed again." |
| `finish` | a linked session first ends (`add_events`) | queued | "You finished a block on Ch2 … (measured 48 min)." |
| `assessment` | assessment create, update, delete | queued | "COS330 Exam changed." |
| `topic` | topic create, rename, move, delete, the planning PATCH; topic review merge, dismiss, restore, and unlinking a page | queued | "A topic in COS330 changed." |
| `availability` | rules, exceptions, planning settings | queued | "Your study time changed." |
| `material` | the end of `link_topics` for a module | queued | "New material was processed for COS330." |
| `nightly` | the worker, once per user per local night | queued | "Updated overnight." |
| `manual` | `POST /plan/replan`, the CLI's `--persist` | inline | "Re-planned on request." |

- **Coalescing:** `enqueue_replan` is `INSERT … ON CONFLICT DO NOTHING` on the partial unique index, in the caller's
  transaction (a job exists exactly when its change commits). While a re-plan job runs, a new change queues the next
  one. A coalesced job keeps its first trigger.
- **Nightly:** `queue_nightly_replans(session, now)` queues a re-plan for each user whose current version's
  `checked_at` is before their most recent local 03:00, unless one is already queued or running. Users with no
  version are skipped. The worker's loop calls it at most once a minute.
- **Starting a planned block:** `POST /sessions` takes `plan_block_id`. The block must be the user's (else 404), a
  planned block of the current version (else 409), and match the session's module and topic (else 422).

## Alternatives considered

| Option | Why not |
| --- | --- |
| Overwrite one plan in place | No history for the consistency metric, and no way to explain a change |
| A new version on every run | The nightly run alone would add one a day per user with nothing changed; the report differs as time passes |
| Fix nothing; re-plan everything | Tonight's blocks would move whenever anything changed, the thing a student can least plan around |
| Fix the whole day instead of 24 h | Around midnight "today" is nearly over; 24 h is the same horizon at any hour |
| A Python-side lock or `SELECT … FOR UPDATE` on the user row | The advisory lock needs no row, ends with the transaction, and covers the first version too |
| Let the planner reuse a skipped slot | It did, in the first test run: the skipped block came straight back at the same time |

## Consequences

- `GET /plan` is the one GET with a side effect (it creates version 1).
- A re-plan job's failure has no `on_failure` message; the current version stays until the next run.
- A fixed block in progress whose session is open counts once as a fixed block and again as today's measured minutes
  against the cap. That's conservative (less new study today), and rare.
- Fixtures in tests clear the re-plan jobs their setup queued (`forget_replans`); job tests that run the real link job
  now count the re-plan it queues.
