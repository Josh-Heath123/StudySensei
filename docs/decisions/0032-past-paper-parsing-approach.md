# 0032: Past-paper parsing approach (from S2)

- **Date:** 2026-11-26
- **Status:** Accepted. Chooses the prompts and schemas for Phase 6 task 3; builds on 0002 (free tiers), 0007 and 0008
  (busy models and refusals).

## Context

Phase 6 learns how a module is assessed from its past papers: each paper is split into its marked parts, and each part
is mapped to the module's topics and given a question type. Spike S2 measured how well free-tier models do that on real
COS330 papers (`docs/spikes/s2-past-papers.md`) against a hand-built key (`evals/pastpapers/cos330.yaml`, a draft for
the reviewer to confirm). The roadmap's targets are segmentation at least 90 % and topic agreement at least 80 %.

Of the 8 ST1 papers in the app, 3 are someone's marked online submission on every page, and one has 13 pages of
handwritten marked answers. They (and those pages) were excluded before any AI call; 5 papers, 103 parts, were used.

## Decision

**Per paper, in this order:**

1. **Transcribe** with the vision role (Flash-Lite first) each page that is flagged scanned or whose text layer has
   fewer than 200 characters, one call per page, with `TRANSCRIPTION_SYSTEM` (it says marks sit at the right margin and
   matter most). Measured: 17 of 17 pages, every key label and mark present.
2. **Segment the whole paper in one call** (candidate A): role `long`, `segmentation_messages` with `PARTS_RULES` (v2:
   full-path numbers, shared-mark items are one part, skip memos), schema `Segmentation`. Measured: **98.1 %** of parts
   with number and marks right, 3 of 3 printed totals, 93 s for 5 papers.
3. **Qualify numbers in code:** a bare label under a parent ("a" under "2") becomes "2.a" (`metrics.qualify`).
4. **Classify the whole paper in one call** (candidate C1): the part numbers and every topic of the module as short
   codes, schema `PaperClassification` (1 to 3 codes, best first, and a type). Codes not in the list are dropped in
   code. Measured: **88.1 %** chapter agreement (92.0 % on parts with a good-fit topic), 66.3 % at subtopic level,
   61.4 % on type.

End to end, the right chapter for 89 of 103 key parts (86.4 %). Both targets are met.

**Around it:**

- Names printed on a paper (titled names, "Examiner:" lines) are redacted from text and masked on images before
  sending; a paper matching the owner's submission pattern is refused before any call.
- Checks in code before anything is saved: the parts' marks against the printed total, repeated numbers, anchors
  (first words) not found in the page text, and pages that yielded no parts.
- The prompts and schemas start from `apps/api/spikes/s2_pastpapers/prompts.py` and `schemas.py`.

## Alternatives considered

- **B, page by page with carry-over** (role `smart`, for models with small per-minute limits): 85.4 % at best, and 7
  times slower on Groq's 8,000 tokens a minute. It loses track of restarted item numbers at page breaks (43.5 % on one
  paper). Kept only as the fallback when the whole-paper call fails twice.
- **C2, per part with the 8 topics nearest by embedding:** 53.0 % chapter agreement. Its candidates held the key's
  chapter for only 79 of 101 parts, a ceiling below the target, and it costs one call per part (103 against 5).
- **Trusting the paper's printed chapters:** the old papers follow an older textbook; on the one paper that prints them,
  6 of 7 differ from today's tree.

## Consequences

- A paper costs about 2 calls plus one per scanned page, within Flash-Lite's daily budget even for a module's whole
  archive.
- Gemini was overloaded for much of the spike (HTTP 503), and fallbacks to Groq worked, but Groq's JSON mode can answer
  HTTP 400 ("failed to generate/validate JSON"), which the client treats as a refusal and doesn't fall back from: one
  paper failed that way in run 2. Task 3 should treat that 400 as "try the next route".
- The question type is the least reliable field (apply, recall and explain are often all defensible), so the correction
  screen makes it a one-click change, and the profile should lean on chapters and marks before types.
- Questions from an older syllabus may have no good topic; the correction screen offers "no good topic" instead of
  forcing one, and such parts stay out of the profile.
- The key is a draft until the reviewer spot-checks it; Phase 6's `evals/pastpapers` starts from it.
