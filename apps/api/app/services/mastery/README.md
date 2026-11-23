# Topic mastery (v1, ADR 0027)

## What it is and isn't

Mastery is an **estimate of how well you know a topic now**, from your own practice and ratings: a number from 0 to 1,
a band (weak, developing, strong) and one sentence saying what it rests on.

It is **never an exam prediction**. It says nothing about the marks you'd get, how a paper will be set, or which
topics will be examined. It is always labelled *estimated*, with its sample sizes, and with fewer than 3 attempts the
app says there isn't enough practice yet instead of showing a band.

It's ordinary, deterministic code: no AI computes or changes it, and nothing is stored. It's computed on read from the
logs, so any past value can be recomputed (Phase 8's trends lose nothing).

## Files

| File | What it does |
| --- | --- |
| `constants.py` | Every constant, named, in one place |
| `formula.py` | Pure: per-item summaries, the prior, the value, status, band and sentence. No database, no clock |
| `load.py` | Read-only, user-scoped: loads one module's inputs, summarises each item once, computes every topic |
| `app/api/mastery.py` | `GET /modules/{id}/mastery` (every topic, tree order) and `GET /topics/{id}/mastery` |

## Inputs and where they come from

A topic covers its **subtree** (decision 0019): its own items and those of every subtopic, each item counted once.

| Input | Source | Notes |
| --- | --- | --- |
| Recall M | `reviews.state_after` (the latest scheduled review of each item up to `at`) | Active items only. The same state `practice_item_states` holds when `at` is now. R from `scheduling.retrievability`, the one FSRS call site |
| Review attempts | `reviews` (`grade`, `reviewed_at`) | Every item that isn't rejected (a suspended item's answers still count). Items with no topic belong to no subtree |
| Quiz attempts | `messages.quiz`, `messages.quiz_answers` in `conversations` whose `topic_id` is in the subtree | Graded by code (`tutor.quiz.grade`), dated by the message's `updated_at` (when the picks were saved) |
| Session rating | `session_topic_ratings` joined to `study_sessions` | The latest, by the session's `reflected_at`, else `ended_at`, else `started_at` |
| Starting confidence | `topics.confidence` | Self-rated 1 to 5, never inferred |
| The local day | `users.timezone` | For "first review of an item on a day" and `days_spanned` |

## The formula

As of a time `at`:

1. **Recall M**: the mean FSRS retrievability at `at` over the subtree's active items that have a state. None if no
   item has been reviewed. `m` is that count (`items_reviewed`).
2. **Attempts**: the first review of each item on each local day, scored Again 0, Hard 0.5, Good 1, Easy 1; and each
   answered Quiz me question, right 1, wrong 0. Later reviews of an item the same day are learning-step repeats, not
   attempts. `n` is the number of attempts (unweighted).
3. **Accuracy A**: the mean score weighted by `0.5^(age / 30 days)`, the age measured from the newest attempt. Because
   the weights are relative, A doesn't change while no new attempts arrive.
4. **Prior P**: the latest session rating, else the starting confidence (the sentence names which: "your latest
   session rating", "your starting rating", "your subtopics' mean rating"); a topic rated neither way uses the mean of its
   rated subtopics (each rated the same way), rounded half up, as the planner's `subtree_confidence` does. P =
   (c − 1) / 4. Unrated: P = 0.5, and the sentence says "no rating yet (50 % assumed)".
5. **Weights**: `w = n / (n + 3)` (attempts against the prior) and `g = m / (m + 3)` (recall's own sample).
6. **Value**:

   ```
   A' = w·A + (1 − w)·P                 accuracy, shrunk to the prior
   value = 0.6·g·M + (1 − 0.6·g)·A'     recall carries up to its 0.6 share as its sample grows
   ```

   With no recall it's `A'` (A alone, as for a quiz-only topic); with no attempts it's `P`. As both samples grow it
   tends to `E = 0.6·M + 0.4·A`.
7. **Status**: `not_enough` when n < 3 (the value is still computed, for task 5), else `estimated`.
8. **Band**: weak < 0.5 ≤ developing < 0.8 ≤ strong.

### The constants, and why

| Constant | Value | Why |
| --- | --- | --- |
| `RECALL_SHARE` / `ACCURACY_SHARE` | 0.6 / 0.4 | Recall is FSRS's model of every item's memory now and decays on its own; accuracy is what you actually got right, but lags and doesn't decay. Recall leads because "now" is the question |
| `PRIOR_ATTEMPTS` (k) | 3 | Your rating counts as 3 attempts: it steers a topic you've barely practised and fades fast (under 10 % of the weight by 30 attempts) |
| `HALF_LIFE_DAYS` | 30 | About a month: a semester's recent work dominates without discarding older answers |
| `MIN_ATTEMPTS` | 3 | Below 3, one lucky or unlucky answer would swing the band; matches PRODUCT's "3 attempts per topic" |
| `DEVELOPING_FROM` / `STRONG_FROM` | 0.5 / 0.8 | 0.8 is close to FSRS's 0.9 target retention less a margin; below 0.5 you'd miss more than you'd get |
| `GRADE_SCORES` | 0, 0.5, 1, 1 | Hard is a slow, partial recall; Easy is no more correct than Good |
| `UNRATED_PRIOR` | 0.5 | No information either way |

### Why recall has its own weight g

The first draft was `value = w·E + (1 − w)·P` with `E = 0.6·M + 0.4·A`. Its monotonicity property failed at once: with
M above P (a topic rated 1 whose one card still had some recall), a *wrong* quiz answer raised the value, because the
extra attempt raised `w` and so the weight on M, which a quiz answer can't move. Any formula where an attempt raises
recall's weight has this flaw. So the prior shrinks only accuracy, and recall's share grows with its own sample. ADR
0027 records it.

## Worked examples

All three use the defaults above and UTC.

**1. A new topic you rated 2 at the start.** No reviews, no quiz. n = 0, so the value is P = (2 − 1) / 4 = **0.25**
(weak), status `not_enough`:

> Not enough practice yet: 0 of 3 attempts. Your starting rating of 2 of 5 is used for now.

**2. Ten good reviews.** Ten new cards, each answered Good once on Monday from 18:00, rated 3 in that session's
reflection; seen on Tuesday at 20:00 (FSRS counts whole days since a review: one each).

- M: each card has stability 2.31 days, so R after 1 day = 0.9468; M = **0.947**, m = 10, g = 10/13 = 0.769
- A = 1.0 (ten attempts, all right), n = 10, w = 10/13 = 0.769; P = 0.5
- A' = 0.769·1 + 0.231·0.5 = 0.885
- value = 0.6·0.769·0.947 + (1 − 0.462)·0.885 = 0.437 + 0.476 = **0.913** (strong)

> ≈ 91 % (estimated) from recall of ≈ 95 % across 10 practised items, 10 of 10 recent answers right, and your latest
> session rating of 3 of 5.

**3. The same topic, untouched for 30 days.** Seen 31 days after the reviews instead: R = 0.664 each, so M = **0.664**.
A, n, w, g and P don't move (no new attempts).

- value = 0.462·0.664 + 0.538·0.885 = 0.307 + 0.476 = **0.783** (developing)

> ≈ 78 % (estimated) from recall of ≈ 66 % across 10 practised items, 10 of 10 recent answers right, and your latest
> session rating of 3 of 5.

Tests: `tests/mastery/test_formula.py` (`test_worked_example_*`).

## Properties (Hypothesis, `tests/mastery/test_formula.py`)

- The value is always in [0, 1].
- A new right answer (no older than any other attempt) never lowers it; a new wrong one never raises it.
- With no new attempts, it never rises as time passes (R only decays; A and n don't move).
- With n = 0 it is P; the more attempts, the less a rating change moves it (at n = 30, 1 to 5 moves it under 0.10).
- An item in both a chapter's tree and its subtopic counts once.
- Same-day repeats don't change n; a quiz-only topic uses A alone; any input order gives the same result.

## Edge cases

- **Learning steps:** an Again and then a Good 10 minutes later is one attempt (scored 0), two reviews.
- **Whole days:** FSRS's R counts whole days since the last review, so it's 1.0 for the first 24 hours and steps
  down daily.
- **Suspended items:** their answers count as attempts; their recall doesn't (M is over active items).
- **Rejected items** count for nothing (they were wrong or unclear). **Items with no topic** belong to no subtree.
- **Reviews from before scheduling** (task 1, no `state_after`) are attempts but give no recall.
- **A backdated attempt:** the monotonicity property is for a new attempt. A correct answer older than the others has
  little weight in A but still raises w, so it can lower the value slightly when A is below P.
- **Quiz timing:** a quiz's picks can be changed; all are dated by the last save, and only answered questions count.
- **A deleted topic** leaves its items with no topic and its conversations with no topic: neither counts anywhere.
- **Time zones:** the local day comes from `users.timezone` as of now; changing it re-buckets past reviews.
- **Order:** items are de-duplicated by id and every sum is `math.fsum`, so input order can't change a bit.

## What tasks 4 and 5 will use

- **Task 4 (practice UI):** the band and `basis` per topic (`GET /modules/{id}/mastery`), the counts in `samples` to say
  what's been practised, and `not_enough` to invite three more attempts.
- **Task 5 (Quiz me and the planner):** `value` (computed even when `not_enough`) to point Quiz me at weak topics and to
  weight planner priority toward them; `status` and `samples.attempts` to decide how much to trust it. The planner's
  inputs and rules don't change in this task.

## Changing a constant

Every constant lives in `constants.py`. Changing one changes what students see for every topic, so it needs a new
ADR (superseding the relevant part of 0027) saying what changed and why, with the worked examples and the property
tests updated in the same PR. No value is stored, so there is nothing to migrate: the next read uses the new
constant.
