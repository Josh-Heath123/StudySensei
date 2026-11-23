# 0027: Topic mastery v1

- **Date:** 2026-11-23
- **Status:** Accepted. Amends 0026 (the review list's fields and the queue's counts).

## Context

Phase 5 task 3: a number for how well the student knows each topic, which the practice UI (task 4) shows and Quiz me
and the planner (task 5) will use. PRODUCT lists it as *estimated*, from the FSRS memory model, practice accuracy and
self-confidence, with 3 attempts per topic as the minimum. It must be ordinary, deterministic code (no AI), tested
with properties, and never presented as an exam prediction.

## Decision

### What it is

An estimate of how well the student knows a topic **now**, from 0 to 1, with a band and a code-written sentence that
labels every number. Never an exam prediction. `services/mastery/README.md` is the full description, with worked
examples; `constants.py` holds every constant.

### The formula (`services/mastery/formula.py`, pure)

For a topic's subtree (decision 0019, each item once), as of `at`:

- **Recall M:** mean FSRS retrievability at `at` over the active items with a state (`scheduling.retrievability`, the
  single FSRS call site); `m` items. None if none.
- **Attempts:** the first review of each item on each local day (`users.timezone`), Again 0, Hard 0.5, Good 1, Easy 1;
  and each answered Quiz me question in a conversation whose topic is in the subtree, right 1, wrong 0 (graded by
  code). Later same-day reviews are learning-step repeats, not attempts. `n` attempts, unweighted.
- **Accuracy A:** the mean weighted by `0.5^(age / 30 days)`, age measured from the **newest attempt**, so A is a pure
  function of the attempts and doesn't move while none arrive.
- **Prior P:** the latest session reflection rating, else the starting confidence; a topic rated neither way uses the
  mean of its rated descendants (each resolved the same way), rounded half up like `subtree_confidence`. (c − 1) / 4;
  unrated is 0.5, flagged.
- **Value:** `w = n / (n + 3)`, `g = m / (m + 3)`, `A' = w·A + (1 − w)·P`, `value = 0.6·g·M + (1 − 0.6·g)·A'`. No recall:
  `A'`. No attempts: `P`.
- **Status:** `not_enough` below 3 attempts (value still computed), else `estimated`. **Band:** weak < 0.5 ≤
  developing < 0.8 ≤ strong.
- **Output:** value, status, band, components {recall, accuracy, prior, weight, recall_weight}, samples
  {items_reviewed, items_active, attempts, quiz_answers, reviews, days_spanned, rating_source}, and `basis`, e.g.
  "≈ 91 % (estimated) from recall of ≈ 95 % across 10 practised items, 10 of 10 recent answers right, and your rating
  of 3 of 5." or "Not enough practice yet: 2 of 3 attempts. Your rating of 3 of 5 is used for now."

### The deviation from the task's formula, and why

The task specified `value = w·E + (1 − w)·P` with `E = 0.6·M + 0.4·A` (or M or A alone). Written that way first, the
Hypothesis property "adding a wrong attempt never raises mastery" failed on its first run: one card reviewed Again
100 days earlier (M ≈ 0.39, A = 0), rated 1 (P = 0), then one wrong quiz answer: the value went from 0.058 to
0.093. The extra attempt raised `w`, which moved weight from P onto E, and E's recall part is something a quiz answer can't change.
The mirror case (a right answer lowering the value when E < P) fails the same way. It isn't a tuning problem: any
formula in which an attempt raises recall's weight has it.

So the prior shrinks only accuracy (by `w`, from the attempts), and recall carries its 0.6 share scaled by its own
sample (`g`, from the items reviewed). This keeps everything the task asked for: P alone at n = 0; A alone for a
quiz-only topic (`w·A + (1 − w)·P`, exactly the task's formula there); E as both samples grow; a rating change moves
the value by at most `(1 − w)`, under 0.10 at 30 attempts. And every property now holds (each run at 5,000 examples
while developing).

The monotonicity property is stated for a **new** attempt (no older than any other). A backdated correct answer has
little weight in A but still raises `w`, so it can lower the value slightly when A < P; the README lists it.

### Computed on read; nothing stored

`services/mastery/load.py` loads one module's topics, items (never rejected; topicless items belong to no subtree),
their reviews up to `at`, its conversations' answered quizzes, the session ratings and starting confidences; it
summarises each item once and computes every topic. Recall comes from the latest `reviews.state_after` up to `at`, not
from `practice_item_states`, so a past `at` is computed exactly. Quiz answers are dated by the message's `updated_at`;
session ratings by the session's reflection, else end, else start.

There's **no `topic_mastery` table in v1**: the logs (append-only reviews, messages, ratings) can recompute any past
value, so Phase 8's trends lose nothing, and there's no cache to invalidate when a review, quiz or rating lands. A
module with 60 topics and 600 items (1,800 reviews) computes in about 33 ms (the test requires under 200 ms). A stored
snapshot can come later if trends need it, as a derived table rebuilt from the logs.

### API and UI

- `GET /modules/{id}/mastery` → `{module_id, at, topics: [...]}`, every topic in tree order; `GET /topics/{id}/mastery`
  → one. Both 404 for another user's module or topic, with cross-user tests.
- The topic dialog shows one read-only line under Starting confidence: the band chip (Weak, Developing, Strong) and
  the basis sentence, or only the "Not enough practice yet" sentence.
- The planner's inputs and rules don't change (task 5).

### From the post-merge review of #49

- `GET /practice/items/{id}/reviews`: each review gains `desired_retention` and `after {state, due}` (from
  `state_after`; null on task 1's reviews), for the practice screen's "next due". `scheduled_days` was already there.
- Queue counts: `new_today_left` stays `min(allowance left, new items available)` (0 with no new items, even when 17 of
  20 are allowed) and `new_allowance_left` is added: `practice_new_per_day` less the new items first reviewed today,
  never below 0.

## Alternatives

- **The task's formula as written:** fails monotonicity (above).
- **Recall unshrunk (`0.6·M + 0.4·A'`):** monotone too, but one review would give recall its full 0.6 share, and R is
  near 1 for the first day after any review, so one card would jump a topic to strong.
- **Recency-weighted n:** makes the prior regain weight as time passes, so mastery could *rise* with no practice.
- **Weights from the time of computing (`at`) rather than the newest attempt:** the same maths, but floating point
  then lets A drift by a last bit as time passes, which breaks the time property for no benefit.
- **A stored, nightly table:** stale between runs, invalidation on every review, and nothing it can say that the logs
  can't.

## Consequences

- Every constant is in `constants.py`; changing one needs a new ADR, with the worked examples and properties updated.
- `components` has a fifth field, `recall_weight` (g), beyond the task's {M, A, P, w}.
- Mastery reflects whatever practice exists: a topic practised only through Quiz me rests on accuracy and the rating.
- Phase 8 can compute trends by calling the same code at past times.
