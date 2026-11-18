# Evals

Fixed yardsticks for the AI and search features, run **locally against the dev database** (the real
COS330 data). They never run in CI and never call an AI provider: search and linking use the local
embedding model, and the topic eval only reads what's stored. The database session is read-only in
Postgres itself (`default_transaction_read_only`), so an eval can't write.

Run them from the repo root with the Docker database up (`npm run db:up`; `npm run dev` can be stopped):

| Eval | Command | What it measures |
| --- | --- | --- |
| Search | `uv run --directory apps/api python -m evals.search cos330` | Each query's rank of the first acceptable page and slide; slide in the top 3, any acceptable page in the top 3, MRR. **Pass:** any acceptable page in the top 3 for ≥ 12 of 15 (exit code 1 otherwise) |
| Linking | `uv run --directory apps/api python -m evals.linking cos330` | The current similarity links (count, near-empty pages, same vs cross-chapter), then a sweep of link rules re-scored the way `linking.py` does |
| Topic extraction | `uv run --directory apps/api python -m evals.topic_extraction cos330` | The current tree against the reviewed reference (matched, missing, extra, moved), and citation precision per material kind |

`... python -m evals.topic_extraction cos330 --export` rewrites the reference from the dev database
(after a deliberate review, not to make the eval pass).

## What's committed, and what isn't

Committed: queries, material titles, page numbers, topic names, chapter patterns and numbers.

- `cos330.yaml`: the module code and its chapter mapping (a material's chapter from its title, a
  topic's from its top-level "ChN" ancestor). Shared by the linking and topic evals; app code knows
  nothing about chapters.
- `search/cos330.yaml`: 15 queries, each with its acceptable pages (material title, page, slide flag).
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

## Baseline, 18 Nov 2026 (COS330, after PR #26's relink)

- **Search:** slide in the top 3 for 11/15; any acceptable page in the top 3 for 15/15 (PASS); MRR 0.900.
  In each of the four slide misses the student's own notes page on that concept ranked first.
- **Linking (subtopics):** 551 cited and 310 similarity links (scores 0.67–0.88); 0 on near-empty pages;
  201 same-chapter, 91 cross-chapter, 18 no chapter. Chapter topics: 543 cited, 50 similarity.
  - The 0.63 threshold never cuts: 0.67 keeps all 310.
  - 0.75 keeps 88 % of same-chapter and 48 % of cross-chapter links; 0.76 keeps 79 % and 30 %; 0.78
    keeps 56 % and 5 %. Relative and cap rules are worse than a global threshold at every level.
  - No rule drops most cross-chapter links while keeping 85 % of same-chapter ones, so the defaults
    (0.63, cap 12) are unchanged.
- **Topic extraction:** 58 of 58 reference topics matched, none missing or extra. Citation precision by
  chapter: slides 716/716, notes 318/319 (Ch8 notes 106/106), study guide 59 not scored.
