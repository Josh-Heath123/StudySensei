# 0016: A topic's workload is estimated from its pages, at 3 minutes a slide and 6 a page of text

- **Date:** 2026-11-20
- **Status:** Accepted.

## Context

The planner (Phase 4) needs to know how long each topic takes. Students rarely know this up front, and asking for a
number per topic before any plan exists is a chore that most will skip. Every topic already has linked material
pages (`chunk_topics`, by cited page or by meaning; decision 0006), and each material has a kind (slides, notes,
study guide and so on). Pages of different kinds take very different times: a lecture slide has one idea in a few
lines, while a page of notes or a study guide is a full page of prose.

## Decision

1. **The default is computed, never stored.** It's computed when the topic tree is read
   (`services/planning/workload.py`), so it follows the links as they change, and it's always labelled "estimated"
   with what it came from ("≈ 2 h, estimated from 18 slides").
2. **The rates:**
   - **3 minutes a slide** (`slides`). Reading it, making sense of the diagram or code, and a line of notes. A
     45-minute lecture of about 30 slides then comes to about 1.5 h of study, close to the common advice of one to two
     hours of self-study per lecture hour.
   - **6 minutes a page of text** (`notes`, `study_guide`, `tutorial`, `other`). A full page is about 400 to 500 words.
     Read for understanding at around 100 to 150 words a minute, that's about 3 to 5 minutes, plus a minute or two to
     note or summarise it.
   - **Not counted:** past papers, tests, assignments and outlines. They're practice or admin, not material to learn.
     Practice gets its own time in Phase 5.
3. **Distinct pages per topic.** A page linked twice to one topic counts once. A page linked to two topics counts in
   both, because each topic still has to be studied.
4. **The total is rounded up to 5 minutes.** With no linked page of a counted kind, there's no estimate ("No
   estimate yet"), never a made-up default.
5. **The student's own figure wins** (`topics.estimated_minutes`, 5 to 6,000 minutes). It's shown as theirs, and
   clearing it goes back to the estimate.

## Alternatives considered

| Option                                      | Why not                                                                                                             |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| One rate for every page                     | Over-counts slide decks (often 40+ thin pages) and under-counts dense notes                                         |
| Characters or words per page (`char_count`) | Closer for prose, but slides with code or diagrams have few characters and take long; harder to explain in one line |
| Ask the AI how long a topic takes           | Not grounded, varies from run to run, and the rule is that AI never sets planning numbers                           |
| A fixed default per topic (say 1 h)         | Ignores the material entirely; a one-slide topic and a 40-page chapter would get the same time                      |

## Consequences

- The rates are a starting guess, labelled as one. Once sessions record time per topic (Phase 5–6), a measured rate
  per student can replace them, in a new ADR.
- A topic with no linked pages has no estimate, so the planner (task 2) must handle "unknown" (for example with a
  minimum block, reported in the feasibility report) rather than treating it as zero.
