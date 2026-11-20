# 0019: Planning scope: topic subtrees, course order and assessment kinds

- **Date:** 2026-11-20
- **Status:** Accepted. Amends 0017 (planner v1 rules) and 0018 (study methods and reason text).

## Context

A live review of #43 on COS330 (with temporary test data, since deleted) and the demo run found four problems with
what the planner plans:

- **Double counting.** A test ticked for "Ch5 Database and Data Center Security" and its 5 subtopics needed 9 h 50:
  the chapter's own pages (3 h 40) plus each subtopic's (6 h 10). The chapter's pages largely overlap its subtopics'
  pages, and six topics meant six two-block minimums.
- **Undercounting.** An exam ticked for Ch1–Ch4 counted only the chapter rows' own pages. Ch1 got 2 h 15 from 32 slides
  and 6 pages, though its subtopics link 40 slides and 28 pages more. Ticking a chapter means the whole chapter.
- **Order.** Topics of equal priority were ordered by id, so the exam's first week read Ch1, Ch3, Ch4, Ch2.
- **Kinds.** An assignment got a "final review". An assessment whose topics were all planned for a sooner one read
  "needs 0 min, 0 min planned".

## Decision

### 1. An assessment covers whole subtrees

1. **Covering a topic covers its subtree.** The **planning unit** is each covered topic with no covered ancestor.
   Covered descendants are absorbed into it: nothing is counted twice, and there is one two-block minimum per unit.
2. **Unit workload:** the student's own figure on the unit; else the ADR 0016 estimate over the **distinct** pages
   linked to the unit or any descendant (a page linked to a parent and a child counts once); else none.
3. **Studied minutes:** sessions on the unit or any descendant, summed and then floored to whole minutes. This
   replaces ADR 0018's "a session on a subtopic counts for that subtopic only".
4. **Confidence:** the unit's own rating; else the mean of its rated descendants, rounded half up; else not rated.
5. **A unit inside a sooner assessment's unit is that unit.** If a test ticks Ch1 and a later assignment ticks one of
   Ch1's subtopics, the assignment's unit becomes Ch1, so the planner plans it once, for the test (ADR 0017 rule 5).
6. **The same code everywhere.** `services/planning/subtree.py` holds the pure rules. The planner's inputs and the
   topic tree API's `workload_with_subtopics` (for every topic with children) both use `subtree_workload`, so the
   topic dialog shows the planner's figure.
7. **Reason text names the basis:** "≈ 7 h 15 estimated from 72 slides and 34 pages of text across Ch1 and its 4
   subtopics", and, when confidence is the subtopics' mean, "You rated its subtopics 2 of 5 on average, so it gets
   25 % more time."
8. **What's saved doesn't change.** `assessment_topics` still holds exactly what was ticked. The assessment form shows
   a ticked topic's descendants as included (checked, disabled, "Included with Ch1"), and unticking the parent
   restores each descendant's own state.

### 2. Course order breaks ties

`TopicInput.order` is the topic's index in its module's tree in pre-order (a parent before its children, siblings by
position, then name). Within an assessment, priority is lower confidence, then **course order**, then id. Deadline and
weight still order the assessments first.

No pass needed changing for the first blocks to follow course order. In the spacing pass's first round each unit
takes the earliest spot left, and nothing placed earlier in that round is ever moved.

### 3. Final reviews only for exams, tests and quizzes

Only `exam`, `test` and `quiz` get a final review, and only they can have a `no_review_time` shortfall.
Assignments, projects and `other` still get study blocks for their topics.

In the feasibility report, an assessment that covers topics but has none of its own (all are planned for a sooner
assessment) says so: "COS330 Assignment (5 Dec): its topics are planned for COS330 Semester test (3 Dec)." One whose
topics need no more time says that instead. Neither prints "needs 0 min".

## Alternatives considered

| Option | Why not |
| --- | --- |
| Save the subtree in `assessment_topics` when a parent is ticked | Changes what the student chose. A topic added to the chapter later wouldn't be covered, and unticking couldn't restore the subtopics' own choices |
| Sum the subtopics' workloads (each topic on its own pages) | The same page is counted once per topic it's linked to: Ch5's 9 h 50 |
| Count only covered descendants in a unit | Ticking a chapter means the whole chapter; a partial tick is expressed by ticking subtopics alone |
| Plan each covered topic but subtract overlaps | Still a two-block minimum per topic, and the explanation gets hard to state in one sentence |
| Order ties by name | "Ch10" sorts before "Ch2", and names aren't always numbered; the tree's order is the course's |
| Reviews for every kind | A take-home assignment has no recall moment to review for; its time is better spent on the work |

## Consequences

- On the real COS330 tree (counted read-only from the dev database), ticking a chapter and its subtopics goes from the
  per-topic sum to one unit. Ch5 goes from 9 h 50 (12 minimum blocks) to 4 h 15 (2). Ch1 ticked alone goes from 2 h 15
  (its own pages) to 4 h 20 (36 slides and 25 pages across its subtree).
- A student's own figure on a chapter now means the whole chapter whenever the chapter is ticked. The topic dialog says
  so under "Set your own".
- Known gap: if a **sooner** assessment ticks a subtopic and a **later** one ticks its chapter, the chapter's unit
  still includes that subtopic's pages, which may already be studied by then. Measured sessions subtract what was
  really done. Splitting units across assessments is left for when mastery (Phase 5) gives a better signal.
- The ADR 0017 properties still hold, with assessment kinds and orders drawn at random in the property tests.
