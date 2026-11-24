# Evals

Fixed yardsticks for the AI and search features, run **locally against the dev database** (the real
COS330 data): search (and the tutor's retrieval), linking, topic extraction, the tutor and practice items. They
never run in CI. Search and linking use the local embedding model, and the topic eval only reads what's stored.
**The tutor, practice and practice marking evals are the exceptions**: they make real calls on the free tier (below). The database session is read-only in
Postgres itself (`default_transaction_read_only`), so an eval can't write.

Run them from the repo root with the Docker database up (`npm run db:up`; `npm run dev` can be stopped):

| Eval | Command | What it measures |
| --- | --- | --- |
| Search | `uv run --directory apps/api python -m evals.search cos330` | Each query's rank of the first acceptable page and slide; slide in the top 3, any acceptable page in the top 3, MRR. **Pass:** any acceptable page in the top 3 for ≥ 12 of 15 (exit code 1 otherwise) |
| Retrieval | `uv run --directory apps/api python -m evals.search cos330 --retrieval` | The same queries through the tutor's `retrieve` (at most 8 sources, one per page, `allow_ai` only, the context budget): with no topic, with the query's topic at ×1.25, ×1.5, ×2 and ×3, with only the links a relink at the current threshold keeps, and with a topic from another chapter. Per run: an acceptable page in the 8, its rank (S1 = 1), acceptable pages in the 8, and the context's estimated tokens. No pass mark |
| Linking | `uv run --directory apps/api python -m evals.linking cos330` | The current similarity links (count, near-empty pages, same vs cross-chapter), then a sweep of link rules re-scored the way `linking.py` does |
| Topic extraction | `uv run --directory apps/api python -m evals.topic_extraction cos330` | The current tree against the reviewed reference (matched, missing, extra, moved), and citation precision per material kind |
| Tutor (**real AI calls**) | `uv run --directory apps/api python -m evals.tutor cos330 --label run1 --review <file outside the repo>` | 20 questions through the tutor in answer mode, each with its topic: cited pages, whether one is acceptable, coverage, "doesn't cover" answers, time to first token, the model; then "Quiz me" after 5 of them. Writes `evals/results/tutor-<date>-<label>.json`. **Target:** a correct page cited for ≥ 17 of 20 (85 %), first token under 2 s |
| Practice (**real AI calls**) | `uv run --directory apps/api python -m evals.practice cos330`, then `... python -m evals.practice score cos330` | Practice items written for the 6 topics in `practice/cos330.yaml` (8 each), not stored; a spot-check sheet for a person to mark; then grounded %, and answerable % overall and by kind. **Target:** at least 90 % of at least 30 marked items answerable from their cited source |
| Practice marking (**real AI calls**) | `uv run --directory apps/api python -m evals.practice_marking cos330` | 10 short-answer items written on the fly from the same topics (not stored), three answers each with a known verdict, marked as `POST /practice/items/{id}/mark` does: agreement overall and per expected verdict. Writes `evals/results/practice-marking-cos330.json`. No pass mark |

### The tutor eval

- **Questions:** `tutor/cos330.yaml`. Questions 1–15 are the search eval's (read from `search/cos330.yaml`, with
  their topics and acceptable pages), and 16–20 are its own. "Quiz me" runs after the questions in `quiz_after`
  (5, 12, 16, 17, 18), on that answer's sources.
- **The real service, dry:** each question goes through `build_turn` and `answer`, as `app.tutor.ask --dry-run`
  does. The database session is read-only, and usage is kept in memory, though today's earlier calls still count
  toward the daily budgets. Nothing is stored.
- **Cost:** about 25 free-tier calls a run (20 answers and 5 quizzes, plus any repair or fallback), almost all on
  `groq/openai/gpt-oss-120b`. That's well inside its 1,000 a day, but don't run it in a loop.
- **Pacing:** Groq's free tier allows 8,000 tokens a minute. Before each call the runner waits until the last
  minute's Groq tokens plus an estimate of the request (its text at 3.5 characters a token, plus 1,500 for the
  reply) stay under 7,000. A run takes 10–15 minutes, so start it in the background. Calls turned away anyway are
  counted in the results (`calls`).
- **Timings** start after the pacing wait: they're the tutor's, not the eval's. Retrieval is timed apart.
- **Metrics** (`metrics.py`, unit-tested):
  - **Correct-page citation rate:** answers citing at least one acceptable page.
  - **Coverage:** of the acceptable pages that were among the 8 sources, the share cited. It isn't counted when
    none was among them.
  - **"Doesn't cover":** a heuristic, the system prompt's phrasing with no citations.
  - **Time to first token:** median and 90th percentile, by nearest rank (measured values, never interpolated).
  - **The model mix.**
- **Quiz check:** each quiz records whether its JSON was valid on the first try and how many questions were
  dropped. Whether each marked answer is supported by its cited page, and whether a wrong option is also true, is
  checked **by hand** against the page text and written into the results.
- **What's committed:** `evals/results/` holds numbers, labels and page references only, never answer or course
  text. `--review FILE` writes the answers and the quiz questions for checking; keep that file outside the
  repository.

### The practice eval

- **Topics:** `practice/cos330.yaml` names 6 topics; each gets 8 items through the job's own service (`prepare`, `ask`
  and the filter in `services/practice/generation.py`), on a read-only session with usage in memory. Nothing is
  stored. Calls are paced like the tutor eval's (Groq's 8,000 tokens a minute), so a run takes several minutes.
- **The sheet:** `evals/practice/.local/spotcheck-<date>.csv` (**gitignored**: it holds AI text about the course),
  with columns item, topic, kind, prompt, answer, key points, cited material and page, and an empty `answerable`
  column. Mark each item `y` or `n`: can it be answered from its cited page(s) alone? The run's counts (requested,
  returned, kept, dropped by reason, tokens, time) sit beside it in `spotcheck-<date>.json`.
- **Score:** `python -m evals.practice score cos330` reads the newest sheet with at least one mark and writes
  `evals/results/practice-cos330.json`: items, grounded % (of the items returned, those citing only their given
  sources), marked, answerable % overall and by kind, and whether the target was met (exit code 1 otherwise).
- **What's committed:** the topic names and the results' numbers. Never the sheet.
- **Result (21 Nov 2026, `results/practice-cos330.json`):** 48 items (6 topics x 8), all grounded; marked by hand, 47 of 48
  answerable from their cited pages (97.9 %: flashcards 30 of 30, short answers 17 of 18) against the 90 % target, so
  Phase 5's first Verify line is met. The one failure was a short answer asking *why* something holds where the
  sources only say *that* it does; several answerable items added small facts not on their pages. The generation
  prompt now forbids both (ADR 0026).

### The practice marking eval

- **Items:** for each topic in `practice/cos330.yaml`, 6 items through the generation service (as the practice eval),
  keeping the short answers with at least 2 key points; the first 10, taken in turn from each topic. Nothing stored.
- **Answers with a known verdict:** the reference answer itself (**correct**); the first half of the key points,
  rounded up (2 of 3), copied from them (**partly**: code calls half or more partly); another topic's reference
  answer (**incorrect**).
- **Marking:** `services.practice.marking.mark`, the endpoint's own code: the model judges each key point, code
  derives the verdict. Paced like the tutor eval.
- **Output:** numbers only: cases, agreement % overall and per expected verdict, the full confusion counts, the models
  that marked, calls, tokens and time. No item or answer text, here or in the terminal.
- **Generation counts:** items asked for, returned and kept, short answers, key points the consistency check removed,
  and drops by reason (ADR 0030). A marking turned away as busy waits until its `retry_at` (at most 90 s, 4 tries).
- **Result (24 Nov 2026, `results/practice-marking-cos330.json`):** 30 of 30 (**100 %**): correct, partly and
  incorrect 10 of 10 each, none failed; all marked by Groq's gpt-oss-120b (42 calls, about 11 minutes). Generation:
  36 asked, 36 kept, 12 short answers; the check removed no key point and dropped no item.
- **Before** (23 Nov, ADR 0029): 27 of 30 (90.0 %), correct 7 of 10. The misses were key points their own reference
  answer never stated (ADR 0030).

`... python -m evals.topic_extraction cos330 --export` rewrites the reference from the dev database
(after a deliberate review, not to make the eval pass).

## What's committed, and what isn't

Committed: queries, material titles, page numbers, topic names, chapter patterns and numbers.

- `cos330.yaml`: the module code and its chapter mapping (a material's chapter from its title, a
  topic's from its top-level "ChN" ancestor). Shared by the linking and topic evals; app code knows
  nothing about chapters.
- `search/cos330.yaml`: 15 queries, each with its acceptable pages (material title, page, slide flag) and its
  session topic for the retrieval mode (a subtopic's name and its chapter).
- `topic_extraction/cos330_reference.yaml`: Joshua's reviewed tree, 58 topics as names and parent names.
- `metrics.py`: the pure metric functions, unit-tested in `tests/evals/` (those tests do run in CI).

**Never committed: course text** (no page text, snippets, descriptions or file contents), and nothing
from the student's own submissions. The course files stay outside the repo.

## Definitions

- **Search rank:** the position in the results as the API returns them (one row per chunk, 20 at most).
- **A link:** one (topic, page). A page linked both by citation and by similarity counts as cited.
  Subtopics are reported apart from the 12 top-level chapter topics, whose links are broad by design.
- **Same or cross-chapter:** the page's material chapter against the topic's chapter. The study guide
  and past papers have no chapter, so their pages are "no chapter". Cross-chapter is a proxy for noise,
  not proof: IDS ↔ IPS and buffer overflow ↔ safe coding are real cross-chapter links.
- **Sweep rules:** `global` (a threshold at cap 12), `relative` (also within δ of the topic's best
  cited-page score; topics with no cited pages fall back to the threshold) and `cap`. The table marks the
  rules that keep at least 85 % of the same-chapter links.
- **Citation precision:** the share of AI-cited pages (links with method `pages`) in the topic's own
  chapter. It can't see spill into a *neighbouring section of the same chapter*, which is where the
  notes' citation errors are (the 18 Nov hand check found about 26 of 190 notes and study-guide citations
  wrong); scoring that needs page-to-section labels.

## Retrieval, 18 Nov 2026 (COS330, links as built at 0.63)

| Run | In the 8 | Top 3 | At S1 | MRR | Acceptable pages in the 8 | Boosted sources per query | Tokens mean / max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| No topic | 15/15 | 15/15 | 12/15 | 0.900 | 30 | 0 | 2,063 / 3,530 |
| ×1.25, ×1.5, ×2 | 15/15 | 15/15 | 12/15 | 0.900 | 32 | 5.9 | 2,091 / 3,530 |
| ×3 | 15/15 | 15/15 | 12/15 | 0.900 | 33 | 6.2 | 2,040 / 3,065 |
| Same, links ≥ 0.75 only | as above | | | | 32 (×1.25–×2), 33 (×3) | 5.7 / 6.1 | |
| Another chapter's topic, ×1.25 | 15/15 | 15/15 | 11/15 | 0.867 | 29 | 0.3 | 2,041 / 3,530 |
| Another chapter's topic, ×1.5 / ×2 / ×3 | 15/15 | 15/15 | 9/15 | 0.800 / 0.800 / 0.789 | 29 | 0.3 | 2,041 / 3,530 |

- The three S1 misses (queries 3, 7 and 15) are the same in every run: the student's own notes page on the concept
  (Ch3 notes p8, Ch6 notes p13) and the CH13 slide before the acceptable ones (p12). All are on-topic, so no boost
  can separate them.
- **Chosen:** `TUTOR_TOPIC_BOOST` = 1.25. It gives all of ×2's on-topic gain at the smallest off-topic cost.
- The default context budget (4,500) dropped nothing: the largest context was 3,530 tokens.

## Follow-ups, 19 Nov 2026 (COS330, the query's topic, x1.25)

Three follow-ups asked after queries 5, 12 and 15 (`follow_ups` in `search/cos330.yaml`), each accepted on its
query's pages. "Alone" searches the follow-up's own words; "with context" is the tutor's rule since Phase 3 task 3
(a second search on the previous question and the follow-up, fused by RRF).

| After | Follow-up | Alone: rank (acceptable in 8) | With context |
| --- | --- | --- | --- |
| 5 | how can a database stop that? | 2 (3) | 2 (3) |
| 12 | which of the two is faster? | - (0) | 2 (2) |
| 15 | which one leaves the customer responsible for the most? | 4 (1) | 1 (3) |

An acceptable page in the 8: alone 2/3, with context 3/3. With context, query 12's S1 is still off-topic (Ch7 notes
p38): "faster" pulls in a quantitative page. The pages it needs are S2 and S5.

## Baseline, 18 Nov 2026 (COS330, after PR #26's relink)

- **Search:** slide in the top 3 for 11/15; any acceptable page in the top 3 for 15/15 (PASS); MRR 0.900.
  In each of the four slide misses the student's own notes page on that concept ranked first.
- **Linking (subtopics):** 551 cited and 310 similarity links (scores 0.67–0.88); 0 on near-empty pages;
  201 same-chapter, 91 cross-chapter, 18 no chapter. Chapter topics: 543 cited, 50 similarity.
  - The 0.63 threshold never cuts: 0.67 keeps all 310.
  - 0.75 keeps 88 % of same-chapter and 48 % of cross-chapter links; 0.76 keeps 79 % and 30 %; 0.78
    keeps 56 % and 5 %. Relative and cap rules are worse than a global threshold at every level.
  - No rule drops most cross-chapter links while keeping 85 % of same-chapter ones. The default stayed at 0.63
    then; Phase 3 task 1 adopted 0.75 (it halves the cross-chapter links and keeps 88 % of the same-chapter ones),
    with migration 0016 queuing the relink.
- **Topic extraction:** 58 of 58 reference topics matched, none missing or extra. Citation precision by
  chapter: slides 716/716, notes 318/319 (Ch8 notes 106/106), study guide 59 not scored.
