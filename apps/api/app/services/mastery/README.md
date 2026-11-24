# Topic mastery (v1, ADRs 0027 and 0028)

## What it is and isn't

Mastery is an **estimate of how well you know a topic now**, from your own practice and ratings: a number from 0 to 1,
a band (weak, developing, strong; none until there's enough practice) and one sentence saying what it rests on.

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
| `load.py` | Read-only, user-scoped: loads one module's inputs, summarises each item once, computes every topic; `mastery_by_topic` does several modules in one call (the planner) |
| `app/api/mastery.py` | `GET /modules/{id}/mastery` (every topic, tree order) and `GET /topics/{id}/mastery` |

## Inputs and where they come from

A topic covers its **subtree** (decision 0019): its own items and those of every subtopic, each item counted once.

| Input | Source | Notes |
| --- | --- | --- |
| Recall M | `reviews.state_after` (the latest scheduled review of each item up to `at`) | Active items only. The same state `practice_item_states` holds when `at` is now. R a week after `at`, from `scheduling.retrievability`, the one FSRS call site |
| Review attempts | `reviews` (`grade`, `reviewed_at`) | Every item that isn't rejected (a suspended item's answers still count). Items with no topic belong to no subtree |
| Quiz attempts | `messages.quiz`, `messages.quiz_answers` in `conversations` whose `topic_id` is in the subtree | Graded by code (`tutor.quiz.grade`), dated by the message's `updated_at` (when the picks were saved) |
| Session rating | `session_topic_ratings` joined to `study_sessions` | The latest, by the session's `reflected_at`, else `ended_at`, else `started_at` |
| Starting confidence | `topics.confidence` | Self-rated 1 to 5, never inferred |
| The local day | `users.timezone` | For "first review of an item on a day" and `days_spanned` |

## The formula

As of a time `at`:

1. **Recall M (recall in a week)**: the mean FSRS retrievability **7 days after** `at` over the subtree's active
   items that have a state. None if no item has been reviewed. `m` is that count (`items_reviewed`). Not R at `at`
   itself: py-fsrs counts whole days, so that's 1.0 for a day after any review, even an Again (ADR 0028). After one
   review of a new card, recall in a week is Again 0.58, Hard 0.75, Good 0.81, Easy 0.91.
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
8. **Band**: weak < 0.5 ≤ developing < 0.8 ≤ strong; null while `not_enough`.

### The constants, and why

| Constant | Value | Why |
| --- | --- | --- |
| `RECALL_AHEAD_DAYS` | 7 | Recall is read a week ahead: it shows a review's grade at once, and a week is the span a student plans in (ADR 0028) |
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

**1. A new topic you rated 2 at the start.** No reviews, no quiz. n = 0, so the value is P = (2 − 1) / 4 = **0.25**,
status `not_enough` and no band:

> Not enough practice yet: 0 of 3 attempts. Your starting rating of 2 of 5 is used for now.

**2. Ten cards, Good twice.** Ten new cards, each answered Good on Monday from 18:00 and Good again on Tuesday, rated
3 in that session's reflection; read on Wednesday at 20:00.

- M: recall in a week (next Wednesday) of each card is 0.8937; M = **0.894**, m = 10, g = 10/13 = 0.769
- A = 1.0 (twenty attempts, one per card per day, all right), n = 20, w = 20/23 = 0.870; P = 0.5
- A' = 0.870·1 + 0.130·0.5 = 0.935
- value = 0.6·0.769·0.894 + (1 − 0.462)·0.935 = 0.412 + 0.503 = **0.916** (strong)

> ≈ 92 % (estimated) from recall in a week ≈ 89 % across 10 practised items, 20 of 20 recent answers right, and your
> latest session rating of 3 of 5.

**3. The same topic, untouched for 30 days.** Read 30 days after Tuesday's reviews: recall in a week is 0.7594 each,
so M = **0.759**. A, n, w, g and P don't move (no new attempts).

- value = 0.462·0.759 + 0.538·0.935 = 0.350 + 0.503 = **0.854** (strong)

> ≈ 85 % (estimated) from recall in a week ≈ 76 % across 10 practised items, 20 of 20 recent answers right, and your
> latest session rating of 3 of 5.

And the case that led to ADR 0028: four new cards, no rating, each answered Again. Three read **35 %** ("recall in a
week ≈ 58 % across 3 practised items, 0 of 3 recent answers right"); the fourth Again lowers it to **34 %**. With
recall read at `at`, they read 47.5 % with "recall of ≈ 100 %", and the fourth Again raised it.

Tests: `tests/mastery/test_formula.py` (`test_worked_example_*`, `test_three_agains_read_as_weak_and_a_fourth_lowers_it`).

## Properties (Hypothesis, `tests/mastery/test_formula.py`)

- The value is always in [0, 1].
- A new right answer (no older than any other attempt) never lowers it; a new wrong one never raises it.
- One more review of one item at a fixed time: Again ≤ Hard ≤ Good ≤ Easy.
- An Again on an item already reviewed never raises it, unless FSRS raises that item's own recall in a week (below).
- With no new attempts, it never rises as time passes (R only decays; A and n don't move).
- With n = 0 it is P; the more attempts, the less a rating change moves it (at n = 30, 1 to 5 moves it under 0.10).
- An item in both a chapter's tree and its subtopic counts once.
- Same-day repeats don't change n; a quiz-only topic uses A alone; any input order gives the same result.

## Edge cases

- **Learning steps:** an Again and then a Good 10 minutes later is one attempt (scored 0), two reviews.
- **Whole days:** FSRS's R counts whole days since the last review, so R at `at` is 1.0 for the first 24 hours and
  steps down daily. Reading it a week ahead is what makes a grade show at once.
- **An Again can raise it (FSRS re-exposure):** FSRS models the exposure itself as building memory. An Again leaves a
  card about 0.5 to 0.58 recall in a week, so on a card whose own recall in a week was below that, the Again raises
  M, and with a low prior the value can follow: a new card on a topic rated 1 (0 → 0.087), a card failed and left
  for 20 days (0.062 → 0.074), or untouched for a month or more. The review asked for "except on an item untouched
  for over 30 days"; the property failed inside 30 days too, so it's stated on the item's own recall instead
  (ADR 0028).
- **Suspended items:** their answers count as attempts; their recall doesn't (M is over active items).
- **Rejected items** count for nothing (they were wrong or unclear). **Items with no topic** belong to no subtree.
- **Reviews from before scheduling** (task 1, no `state_after`) are attempts but give no recall.
- **A backdated attempt:** the monotonicity property is for a new attempt. A correct answer older than the others has
  little weight in A but still raises w, so it can lower the value slightly when A is below P.
- **Quiz timing:** a quiz's picks can be changed; all are dated by the last save, and only answered questions count.
- **A deleted topic** leaves its items with no topic and its conversations with no topic: neither counts anywhere.
- **Time zones:** the local day comes from `users.timezone` as of now; changing it re-buckets past reviews.
- **Order:** items are de-duplicated by id and every sum is `math.fsum`, so input order can't change a bit.

## What uses it

Only an `estimated` value (3 attempts or more) is used anywhere outside this module's own screens; with `not_enough`
the student's rating stands. Nothing writes mastery back.

| Where | What it reads | What it does with it |
| --- | --- | --- |
| The practice screens (task 4) | band, `basis`, `samples`, status (`GET /modules/{id}/mastery`) | `/practice` lists topics weakest first, with a band only when estimated; `not_enough` invites three more attempts |
| The topic dialog | band and `basis` | Shown under Starting confidence (read-only) |
| The planner (task 5, ADR 0031) | `value` and `samples.attempts` per planning unit, over its subtree, at `now` (`mastery_by_topic`, one call per load) | Time `clamp(150 − mastery %, 70, 150)` %; priority (lower first, before course order); reason `low_mastery` below 0.5; a first block's method (first pass below 0.5, active recall from 0.5); the text "≈ 34 % (estimated from 9 answers)" |
| Re-planning (task 5) | (reviews) | Each review queues a re-plan 15 minutes on (trigger `practice`), coalesced to one per sitting |
| Quiz me (task 5, ADR 0031) | `band` of the conversation's topic, at the real clock | The band word only goes in the prompt: weak asks mostly recall, developing a mix, strong mostly application. No number |

None of these presents mastery as a prediction of a mark: the plan says how much time it gives and why, and Quiz me
only picks the question mix.

## Changing a constant

Every constant lives in `constants.py`. Changing one changes what students see for every topic, so it needs a new
ADR (superseding the relevant part of 0027) saying what changed and why, with the worked examples and the property
tests updated in the same PR. No value is stored, so there is nothing to migrate: the next read uses the new
constant.
