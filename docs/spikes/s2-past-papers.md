# Spike S2: past-paper parsing accuracy

- **Date:** 2026-11-26
- **Question:** can free-tier models split real past papers into their marked parts and map each part to the module's
  topics accurately enough for Phase 6 (targets: segmentation at least 90 %, topic agreement at least 80 %)?
- **Answer:** yes, with one whole-paper call per step. Segmentation A (prompt v2, after transcription v2) got
  **98.1 %** of parts exactly right; classification C1 put **88.1 %** of them in the key's chapter. The decision is ADR
  [0032](../decisions/0032-past-paper-parsing-approach.md).
- **Code:** `apps/api/spikes/s2_pastpapers/` (not part of the app; `python -m spikes.s2_pastpapers`). The winning prompts
  are `prompts.py` (`TRANSCRIPTION_SYSTEM`, `PARTS_RULES`, `segmentation_messages`, `paper_classification_messages`)
  and the schemas `schemas.py`: the starting point for Phase 6 task 3. Results (numbers only):
  `spikes/s2_pastpapers/results/cos330.json`.

Numbers only below: no course text, no names.

## Privacy first

- **Submissions:** the 8 COS330 materials of kind past paper or test were checked against the owner's submission
  pattern (by title, file name, and content hash against the matching files in the course folder): **0 matches**.
- **Every page read by hand** (73 pages: the text layer, and the rendered image of each scanned page):

  | Paper | Pages | Pages with personal details or someone's marked work | Used |
  | --- | --- | --- | --- |
  | ST1 2012 | 2 | 0 | all |
  | ST1 2014 | 5 | 0 | all |
  | ST1 2016 | 22 | 13 (pages 10–22: handwritten answers with marking) | pages 1–9 |
  | ST1 2017 | 6 | 0 (the name fields are blank) | all |
  | ST1 2018 | 6 | 0 | all |
  | ST1 2020 | 8 | 8 (a marked online submission: answers, scores, feedback, an attempt ID) | **excluded** |
  | ST1 2023 | 12 | 12 (a marked online submission; page 1 names the student) | **excluded** |
  | ST1 2025 | 12 | 12 (a graded online submission: grade, receipt, answers) | **excluded** |

- **Staff names:** three papers print examiner names (staff, not students). They were redacted from text
  (`privacy.redact_text`: titled names and "Examiner:" lines) and masked on the two page images that show them.
- **What was sent:** 5 papers, 28 pages: 11 text-layer pages and 17 page images. Course text stayed in the spike's
  `.local/` folder (gitignored).

## The answer key

`apps/api/evals/pastpapers/cos330.yaml`, **draft: to be confirmed by the reviewer**. Built by reading the papers.

| Paper | Parts | Marks | Printed total |
| --- | --- | --- | --- |
| ST1 2012 | 11 | 50 | 50 ✓ |
| ST1 2014 | 21 | 60 | none printed |
| ST1 2016 | 33 | 100 | 100 ✓ |
| ST1 2017 | 23 | 60 | 60 ✓ |
| ST1 2018 | 15 | 60 | none printed |
| **All** | **103** | **330** | 3 of 3 printed totals match |

- **Types:** 34 explain, 34 apply, 27 recall, 4 calculate, 4 essay. **Topic fit:** 14 parts are marked `fit: weak`
  (older-syllabus content with no good home in today's tree).
- **The papers are from an older syllabus** (another textbook). ST1 2017 prints a chapter beside each question: 6 of its 7
  printed chapters differ from the key's chapter in today's tree (only its Chapter 1 matches), so printed chapters can't be
  trusted.
- **Against the study guide** (a COS330 material that names chapters for some past questions): where it names a
  chapter, it agrees with the key (threat, vulnerability and control questions in all five papers, and the CIA
  questions in 2017 and 2018, in Ch1; the 2017 and 2018 biometrics questions in Ch3). It disagrees on 4 groups, which
  it calls out of scope with no chapter: buffer overflows (key: Ch10), incomplete mediation and program flaws (Ch11),
  cloud (Ch13) and near-miss analysis (Ch11, weak fit). The list is in the key file.

## Candidates and results

Free tiers only, through `LLMClient` and the existing roles. Three runs; each changed one thing on what it learned.

- **Run 1:** transcription v1, segmentation prompt v1.
- **Run 2:** prompt v2: full-path numbers ("2.a", never a bare "a"; restarted item numbers include the question).
- **Run 3:** transcription v2 (look along the right margin for marks); B gets a page-boundary rule.

"+ qualify" is a code step, not the model: a bare label under a parent ("a" under "2") becomes "2.a".

### Transcription (vision role, 17 scanned or nearly empty pages)

| Version | Pages done | Failed | Key labels found | Key marks found | Calls | Tokens in + out | Time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | 17 | 0 | 59 / 59 | 55 / 59 (93.2 %) | 17 | 20,531 + 3,803 | 90 s |
| **v2** | 17 | 0 | 59 / 59 | **59 / 59** | 17 (+1 turned away) | 21,602 + 3,782 | 90 s |

All 34 by Gemini 3.5 Flash-Lite. v1 lost every right-margin mark on one scanned page, and both segmentations then
missed that page's 4 parts. Two pages of one paper had a text layer of only a heading (under 40 characters) but weren't
flagged as scanned; the spike transcribes any page with fewer than 200 characters.

### Segmentation (103 key parts; exact means number and marks both right)

| Candidate | Run | Exact | + qualify | Printed totals | Calls | Tokens in + out | Time | Failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A: whole paper, role long | 1 | 40.8 % | 52.4 % | 3 / 3 | 8 (+7 turned away) | 26,572 + 9,230 | 112 s | 0 |
| B: page by page, role smart | 1 | 68.0 % | 80.6 % | 3 / 3 | 29 | 39,931 + 12,240 | 582 s | 0 |
| A | 2 | 69.9 % | 69.9 % | 2 / 3 | 6 (+12 turned away) | 9,457 + 6,322 | 335 s | 1 paper |
| B | 2 | 84.5 % | 84.5 % | 3 / 3 | 28 | 41,985 + 12,110 | 643 s | 0 |
| **A** | **3** | **98.1 %** (101) | 98.1 % | **3 / 3** | 10 (+4 turned away) | 32,933 + 12,864 | **93 s** | 0 |
| B | 3 | 85.4 % (88) | 85.4 % | 3 / 3 | 29 | 44,654 + 12,662 | 644 s | 0 |

- **Run 3, per paper:** A got 100 % on four papers and 91.3 % on ST1 2017; B got 100, 95.2, 97.0, 43.5 and 100 %. A also had
  the page right for 101 of 103 parts, and every paper's parts summed to the key's sum.
- **Models:** Gemini was overloaded much of the day (HTTP 503 "high demand"). In run 3 all 5 of A's papers were answered
  by Flash-Lite; in run 2, 4 of 5 fell back to Groq gpt-oss-120b, and one paper failed outright (Gemini busy, then Groq
  answered HTTP 400 "Failed to generate JSON", which the client doesn't fall back from). B is all Groq gpt-oss-120b.
  A's 10 calls for 5 papers include retries after 503s and timeouts and any schema repairs; the run didn't record which.
- **Time:** B is slow because Groq's free tier allows 8,000 tokens a minute, so each page waits its turn.

### Classification (by the key's part numbers; chapter = primary chapter, subtopic = Jaccard ≥ 0.5)

| Candidate | On | Parts answered | Chapter | Subtopic | Type | Chapter, good-fit parts | Calls | Tokens in + out | Time | Failures |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **C1: whole paper, all 58 topics** | **A (run 3)** | 101 / 103 | **88.1 %** (89) | 66.3 % | 61.4 % | 92.0 % of 87 | 7 | 22,246 + 4,598 | 199 s | 0 |
| C1 | B (run 3) | 88 / 103 | 90.9 % (80) | 73.9 % | 67.0 % | 94.8 % of 77 | 5 | 16,745 + 4,136 | 167 s | 0 |
| C2: per part, 8 nearest topics | A (run 3) | 100 / 103 | 53.0 % (53) | 27.0 % | 38.0 % | 57.0 % of 86 | 103 | 76,964 + 9,122 | 970 s | 1 |
| C2 | B | not run | | | | | | | | |

- **End to end** (A, then C1, over all 103 key parts): the right chapter for **89 of 103 (86.4 %)**.
- **C2's ceiling:** the 8 candidates held the key's chapter for only 79 of 101 parts (78 %) and a key subtopic for 57,
  and the nearest topic was in the right chapter for 37. So C2 can't reach 80 % whatever the model picks.
  **C2 on B was not run:** about 100 more paced Groq calls (about 16 minutes) for a candidate its own retrieval already
  rules out.
- **C1's models:** 3 papers by Flash-Lite, 2 by Groq gpt-oss-120b after Gemini 503s. C2 used Groq only; one part failed
  with HTTP 400 "Failed to validate JSON".
- **C1's chapter misses (12 on A):** program-flaw questions from the older syllabus put in Ch1 or Ch10 instead of Ch11
  (7), malware-adjacent questions put in Ch1 (3), and one each Ch1 → Ch4 and Ch1 → Ch3. 5 of the 12 are on weak-fit parts.
- **Type misses (39 on A):** mostly the key's apply read as recall (14) or explain (8), and explain read as apply (7).
  Most are "identify which kind of X this scenario shows" parts, where apply and recall are both defensible: the type is
  the least reliable field, in the key as well as from the model.

## The winning combination per step

| Step | Winner | Why |
| --- | --- | --- |
| Transcription | Vision role (Flash-Lite first), prompt v2 | 17 of 17 pages, every key label and mark present |
| Segmentation | **A**: one call per paper, role `long`, prompt v2, then `qualify` in code | 98.1 % and 3 of 3 totals in 93 s; B tops out at 85 % and takes 7 times as long |
| Classification | **C1**: one call per paper with every topic | 88.1 % chapter agreement (92 % on good-fit parts) in 5 calls; C2's retrieval ceiling is 78 % |

## Failure modes (described, no course text)

1. **Numbers without their parents.** v1 replies gave bare labels ("a" under question 2) or dropped a restarted item
   number (Question 1, item 1, part a → "1.a"). A prompt rule for full-path numbers plus `qualify` in code fixed most;
   the first item of one paper still came back as "1.a" for "1.1(a)" (A's only two misses in run 3).
2. **Lost marks in transcription.** One scanned page lost every right-margin mark, and the segmenters then dropped the
   page's parts. Saying where marks sit, and that they matter most, fixed it (55 → 59 of 59).
3. **Page boundaries (B).** A numbered item at the top of a page was read as a new question, and a page that is a
   figure plus a memo yielded no parts. A carry-over rule helped one paper and not another (ST1 2017: 56.5 % → 43.5 %).
4. **Under-splitting (A, run 1).** One paper's later questions were listed whole, with their totals, not their parts.
5. **Shared-mark items.** A list of items under one total ("a) … e) [10]") is one part; one B run listed its parent too.
6. **Busy free tiers.** Gemini answered 503 many times, and Groq's JSON mode can answer 400 ("failed to generate" or
   "validate JSON"), which the client treats as a refusal, not a busy model, so it never falls back.
7. **Older syllabus.** Questions on content no longer taught have no good topic: 5 of C1's 12 chapter misses.
8. **Type is subjective.** Apply vs recall vs explain is the weakest agreement, between people as well as models.

## What Phase 6 task 3 should build

- **Schemas:** `Segmentation` and `SegmentedPart` (number, parent, marks, page, first words of at most 12),
  `PaperClassification` and `ClassifiedPart` (1 to 3 topic codes, best first, and a type) from `schemas.py`, validated
  before anything is stored. Topics as short codes ("t12") mapped back in code, and codes not in the list dropped.
- **Prompts:** `TRANSCRIPTION_SYSTEM`, `PARTS_RULES` with `segmentation_messages`, and `paper_classification_messages`,
  as they are in `prompts.py`. Redact titled names and "Examiner:" lines before sending.
- **Order of calls, per paper:** (1) transcribe the pages that need it, one vision call per page; (2) one segmentation
  call with the whole paper; (3) `qualify` every number in code; (4) one classification call with the whole paper, the
  part numbers and every topic. A 12-page paper with 2 scanned pages costs 4 calls.
- **When to ask for vision transcription:** for a page flagged scanned, or whose text layer is under 200 characters (a
  heading over an image). Show the page count first (task 2), and only for pages that aren't excluded.
- **Checks in code, shown before saving:** the parts' marks against the printed total (and say when none is printed);
  repeated or missing numbers; parts whose anchor (first words) can't be found in the page text; parts on a page that
  yielded none.
- **Fallbacks:** when the whole-paper call fails twice, fall back to B page by page and say so; treat Groq's 400 JSON
  failures as "try the next route".
- **The correction screen must make easy:** renumbering a part (and its children) in place; splitting a part into
  sub-parts and merging parts, with marks re-summed live against the printed total; editing marks and the page; adding a
  part the model missed by selecting text on the page; changing the type in one click (the least reliable field); and
  changing a topic from a short list (the model's 3 first, then the rest of that chapter), with an "older syllabus: no
  good topic" choice that keeps the part out of the profile rather than forcing a wrong topic.
- **Keep the student's own work out:** before any call, refuse a paper matching the submission pattern; let the student
  exclude pages that hold anyone's answers, marks or name (S2 found 3 of 8 papers were marked scripts throughout).
