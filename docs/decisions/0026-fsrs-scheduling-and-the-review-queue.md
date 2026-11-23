# 0026: FSRS scheduling and the review queue

- **Date:** 2026-11-22
- **Status:** Accepted. Amends 0025 (the review endpoint, the generation prompt, the item output).

## Context

Phase 5 task 2: practice items (ADR 0025) need a schedule, so each comes back when it's about to be forgotten, and a
queue that says what to review now. The roadmap asks that due dates follow FSRS. Scheduling is ordinary code: no AI
decides an interval, and nothing here touches the plan. Mastery (task 3) will read the state this stores.

## Decision

### The library

- **`fsrs` 6.3.3 on PyPI** (py-fsrs, Open Spaced Repetition, MIT), pinned exactly. Its `Scheduler`, `Card`, `Rating`
  and `State` are used as that version's source documents them: default parameters, learning steps 1 and 10 minutes,
  relearning step 10 minutes, a 36,500-day maximum. `review_card` insists on `tzinfo == timezone.utc`, so times are
  converted first; `Card` gets an explicit id (a default one sleeps 1 ms).
- **Fuzzing off** (`enable_fuzzing=False`). With fuzz, the same log gives different due dates, so a stored state
  couldn't be checked by replaying its reviews, a test couldn't pin a date and two devices previewing the same item
  would disagree. Fuzz exists to spread cards learned together over neighbouring days; at our volumes (tens a day)
  that matters little, and it can be added later as a seeded fuzz (from the item id) without losing determinism.
- **No ts-fsrs.** The server computes every interval, including the previews on the grade buttons, so there's one
  implementation to trust.

### The pure core (`services/practice/scheduling.py`)

- `schedule(state | None, grade, at, settings) -> (new_state, scheduled_days)`; grades 1 Again, 2 Hard, 3 Good, 4
  Easy. `None` is a new item. `scheduled_days` is the whole days until due (0 inside learning steps).
- `replay(events, settings) -> state`: a review log in order. Each event carries the desired retention in force when
  it was made, so changing the setting changes only later reviews and a replay still equals the stored state.
- `reps` (reviews) and `lapses` (Again on an item in the review state, FSRS's lapse) are ours: py-fsrs's `Card` doesn't
  keep them. `retrievability` is FSRS's R at a time, shown as **estimated** with the review count as its sample size.
- Tests: a golden test runs fixed timestamps and grades through py-fsrs directly and through `schedule`, and requires
  identical due dates, stability, difficulty and steps ("due dates follow FSRS"). Hypothesis properties: replay equals
  the state built review by review; for one prior state, due(Again) ≤ due(Hard) ≤ due(Good) ≤ due(Easy); due is after
  the review; the same inputs give the same output; snapshots round-trip. None failed, even at 4,000 examples each.

### Data (migration 0026)

- **`practice_item_states`**: one row per reviewed item (no row: new): `state` (learning, review, relearning), `step`,
  `stability` (> 0), `difficulty` (1-10), `due` (after `last_review_at`), `reps` (≥ 1), `lapses` (≥ 0). Primary key
  `item_id`, a composite FK `(item_id, user_id)` that cascades; index `(user_id, due)`.
- **`reviews`** gains `state_before` and `state_after` (JSON snapshots of those fields; before is null for a first
  review), `scheduled_days`, `desired_retention` and `fsrs_version`. All are null on task 1's reviews. The append-only
  trigger stays. `desired_retention` isn't in the task's list; replay needs it, or a changed setting would make a log
  replay to a different state than the one stored.
- **`users`** gains `practice_new_per_day` (0-200, default 20) and `practice_desired_retention` (0.80-0.97, default
  0.90).

### Reviewing

- `POST /practice/items/{id}/reviews` locks the item row (`FOR UPDATE`: the item always has a row, its state may not),
  reads the state (also locked), computes with `schedule` at `clock.now()` and the user's retention, writes the review
  with its snapshots and upserts the state, in one transaction. Two reviews at once are serialised: the second sees
  the first's state. A suspended or rejected item is a 409, "Restore it before reviewing." (it was a 422 for rejected
  in task 1).
- It returns the review, the new due time and days, and the queue's counts (the whole queue, not one module's).
- `GET /practice/items/{id}/preview`: for each grade, the due time and a label ("1 min", "6 min", "10 min", "3 h",
  "1 day", "4 days", "1.5 mo"). Code-written; nothing is stored.
- Every item carries `memory`: state (new, learning, review, relearning), due, stability, difficulty, retrievability
  (estimated, with its sample size), reps, lapses.

### The queue

- `GET /practice/queue?module_id=&topic_id=&limit=` (default 20, at most 100): active items that are due, oldest due
  first; then new active items, oldest first, up to today's allowance: `practice_new_per_day` less the items whose
  first scheduled review (no `state_before`) falls today. "Today" runs from local midnight to the next in
  `users.timezone`, so a DST change gives a 23- or 25-hour day rather than shifting the boundary.
- Counts: `due_now`, `new_today_left`, `new_total`, `next_due_at` (the earliest due after now).
- `GET/PATCH /practice/settings {new_per_day, desired_retention}`; out of range is a 422.
- Learning steps are minutes: an item graded Again comes back in the same sitting, as FSRS intends.

### From the post-merge review of #48

- The spot check (47 of 48 answerable, 97.9 %) found a short answer asking *why* where the sources only said *that*,
  and items adding small facts or examples from elsewhere. The generation prompt now says: ask why or how only when the
  sources give the reason or mechanism; every key point and example must be in the cited sources; add nothing from
  general knowledge.
- Items list their distinct cited `pages` (material and page, in label order), so two passages of one page show once.

## Alternatives

- **ts-fsrs in the browser** for previews: a second implementation that could drift from the server's.
- **Fuzzing on**: closer to Anki's spread, but no replayable log, no pinned test dates.
- **Storing only the state, not snapshots**: a bad state couldn't be traced or rebuilt; with snapshots and the
  retention per review, any state can be checked by replay.
- **A UTC day for the allowance**: wrong by hours for most students; local midnight is what "today" means.

## Consequences

- Changing FSRS's version or parameters changes future intervals only; `fsrs_version` on each review says what
  computed it, and a replay with another version would need its own check.
- `python -m app.practice.simulate` shows the load the defaults give (in memory, synthetic items): about 130 reviews
  (45 active minutes at 20 s each) a day by day 30 at 20 new a day and 0.90 retention, with nothing left due. A student
  who finds that too much lowers `new_per_day`.
- The queue doesn't yet weigh weak topics or upcoming assessments: that's task 5 with mastery.
