# 0011: Large topic-map merges are Gemini-only

- **Date:** 2026-11-18
- **Status:** Accepted. Settles the open question in 0010's Consequences (how to make COS330's merge fit Groq).

## Context

- COS330's merge has 460 proposals. With no descriptions the request is about 27K characters (0010).
- Groq's free tier allows 8K tokens a minute. Even the compact format is over that: the proposal names alone are
  13,336 characters, and the fixed parts add another 6,803, against a budget of 17,500 characters (7,000 tokens at
  2.5 characters a token).
- Making it fit means dropping proposals or changing the format again (ids relative to their material, no page
  counts, or merging in two halves). 0010 left that open.
- A strict-xfail test (`test_a_cos330_sized_merge_fits_its_budget`) kept the question visible.

## Decision

1. **Large merges go to Gemini only.** We don't chase a Groq fit for COS330-sized merges.
   - Merges are rare: once after the materials are analysed, and again when materials are added or the student asks.
   - A busy Gemini (503) only delays a merge, and the job is rescheduled without using up quota or an attempt
     (0008). Nothing is lost by waiting.
   - Dropping proposals would lose topics, and a new format is effort spent on a fallback that's rarely needed.
2. **Groq still takes merges that fit.** Smaller modules keep descriptions while they fit, and Groq stays in the `long`
   role for them (0009).
3. **The over-budget warning stays.** An input over `TOPIC_MERGE_MAX_TOKENS` is logged, not cut (0010), and its tests
   stay.
4. **The strict-xfail test is removed.** It tracked a goal we no longer have.

## Alternatives

- **Relative ids and no page counts:** saves about 4.2K characters, still over budget for COS330, and a larger module
  would overflow again.
- **Merging in two halves:** fits, but two merges can disagree, and anchoring the second to the first adds complexity.
- **Dropping low-value proposals:** loses topics the student never sees, against "the student's review wins" (0009).

## Consequences

- When Gemini is busy, a large merge waits (sometimes hours in the evening) instead of falling back to Groq.
- **If the waits become a problem,** the fix is incremental merges: send only materials added since the last merge,
  anchored to the current tree. That's on the ROADMAP under "Later".
