# 0028: Mastery recall a week ahead

- **Date:** 2026-11-23
- **Status:** Accepted. Amends 0027 (recall M and the band).

## Context

The post-merge review of #50 found two problems with topic mastery v1.

1. **Recall read 100 % right after any review, even an Again.** py-fsrs measures elapsed time in whole days, so FSRS's
   R at the moment of computing is 1.0 for the first 24 hours after a review, whatever the grade. Live, on a topic
   with four of the student's own cards and no rating, three Agains read 47.5 % with the basis "recall of ≈ 100 %
   across 3 practised items, 0 of 3 recent answers right", and a fourth Again raised it to 48.4 %. The monotonicity
   property in 0027 only ever added quiz answers, never a review, so it couldn't catch this.
2. **A band without enough practice.** A topic with no practice and no rating is P = 0.5, on the weak/developing
   edge, and the API returned "developing" for it. The topic dialog hid it, but the API shouldn't say it.

## Decision

### Recall M is recall in a week

M is the mean FSRS retrievability **seven days after** `at` (`RECALL_AHEAD_DAYS = 7` in `constants.py`), still
through `scheduling.retrievability`, over the same items. It answers "how much of this will you still have in a
week", which a review's grade moves at once: after one review of a new card (fsrs 6.3.3, default parameters,
retention 0.9), Again 0.58, Hard 0.75, Good 0.81, Easy 0.91. Ten cards answered Good, and Good again the next day,
read a day later: 0.89; read 30 days after that: 0.76.

The sentence says so: "recall in a week ≈ 81 % across 10 practised items". Nothing else in the formula changes.

### No band while there isn't enough practice

When the status is `not_enough` (fewer than 3 attempts), `band` is null. The value is still computed (task 5 uses
it).

### New properties, with reviews generated

0027's properties only added quiz answers. Two more add a review:

- **A better grade never gives less:** one more review of one item at a fixed time, as Again, Hard, Good and Easy;
  the values are non-decreasing. This passed on the old code too (R was 1.0 whatever the grade).
- **An Again never raises the value**, with one exception. Written first as the task asked, "except on an item
  untouched for over 30 days", it failed before the fix (one wrong quiz answer, no rating, then an Again on a new
  card: 0.375 → 0.405, because R read 1.0). After the fix it still failed, and the 30-day line turned out not to be
  the real boundary. FSRS models the exposure itself as building memory: an Again leaves a card with about 0.5 to 0.58
  recall in a week, so on a card whose own recall in a week was below that, the Again raises it, and with a low
  prior the value can follow. That happens on a new card (rated 1, no practice: 0 → 0.087), on a card untouched for
  a month, and on a card failed and left for weeks (two Agains, then another Again 20 days on, rated 1: 0.062 →
  0.074; 100 days on: 0.050 → 0.075).

  So the property is stated exactly: **an Again on an item already reviewed never raises the value unless FSRS
  raises that item's own recall in a week.** It holds at 5,000 examples, with items generated across the 40 days
  before `at`. Those exceptions are tested as examples and listed in the README.

### The worked examples, redone

| Example | M | Value | Band |
| --- | --- | --- | --- |
| A new topic rated 2 | none | 0.25 | none (`not_enough`) |
| Ten cards Good on Monday and Tuesday, read Wednesday 20:00, rated 3 | 0.894 | 0.916 | strong |
| The same, read 30 days after Tuesday | 0.759 | 0.854 | strong |

The third example was "developing" (0.783) under 0027's recall-now; with two reviews per card, and recall in a
week, it stays strong a month on. The live case above now reads 35 % ("recall in a week ≈ 58 %"), and the fourth
Again lowers it to 34 %.

## Alternatives

- **R now, with whole days made fractional:** R would still be close to 1 straight after any review (an Again's
  stability is about 0.2 days, so R falls fast, but a minute after the review it's still ≈ 1.0). The grade wouldn't
  show for hours.
- **R at the item's next due:** different for every item, and always ≈ the desired retention by construction, so it
  says nothing.
- **Leaving fresh items out of M for a day:** hides practice the student just did, and the value would jump the
  next day.
- **A longer horizon (30 days):** makes everything look weak; a week is the span a student plans in.
- **Keeping the 30-day exception as written:** the property was false within 30 days, as above.

## Consequences

- Mastery reads lower than 0027's right after practice, and a grade shows in it at once.
- `components.recall` is recall in a week; the API's comment says so.
- `band` is nullable in the API and the TS types; the UI shows a chip only when there is a band.
- A month on, recall falls more slowly than under recall-now (the curve's tail is flatter), so the third worked
  example stays strong.
