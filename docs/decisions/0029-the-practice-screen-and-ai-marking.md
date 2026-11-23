# 0029: The practice screen and AI marking

- **Date:** 2026-11-23
- **Status:** Accepted. Amends 0025 (reviews can be marked with the AI's help) and 0026 (the items list's filters).

## Context

Phase 5 task 4: the screens where a student reviews cards, writes their own, and checks a short answer. Flashcards
are self-marked. A short answer can be checked two ways: against the reference answer and its key points (by the
student), or by the AI. The rules that apply: the AI never writes a grade or any progress, its output is used only
after passing a Pydantic schema, nothing about the student goes into a prompt, and every number shown is labelled.

## Decision

### AI marking: `POST /practice/items/{id}/mark`

- **Input:** `{answer_text}` (1-2000 characters). Short-answer items only (422 for a flashcard), active only (409),
  another user's item is a 404. Stores nothing.
- **Call:** the `smart` role, **interactive** (ADR 0013): a busy model is skipped without waiting, and when every
  model is busy the API returns 503 with Retry-After, as the tutor does. Purpose `practice_marking` in `ai_usage`.
  A reply that still doesn't fit after one repair, or a refusal, is a 502 with a readable message ("mark it
  yourself").
- **Prompt** (`services/practice/marking.py`, code only): the question, the reference answer, the numbered key
  points, and the student's answer in a `<student_answer>` tag, marked untrusted. The tag can't be closed from inside
  (`<student_answer` and `</student_answer` are escaped), and the system prompt says never to follow instructions in
  it. The model judges **only whether each key point is present in meaning**, not the wording, and writes one or two
  sentences of feedback that add no fact beyond the reference. Nothing else about the student is sent: the privacy line
  under the button says exactly that ("Sends your answer and the reference answer to the AI to check it. Nothing else
  about you.").
- **Schema:** `{key_points: [{index, covered}], feedback (≤ 300)}`, with exactly one entry per key point 1..n
  (`marking_reply(n)`; anything else is invalid and repaired once). Extra keys, such as a grade the model volunteers,
  are ignored.
- **Code derives the result** (`schemas.practice.verdict_for`): all key points covered is **correct** and suggests
  Good (3); at least half is **partly** and suggests Hard (2); fewer is **incorrect**, suggesting Again (1). Nothing
  suggests Easy. The reply is `{coverage: [{index, key_point, covered}], verdict, suggested_grade, feedback, model}`.

### The student always grades

- `ReviewIn` gains `marked_by` ("self" | "ai", default "self") and `ai_marking` (the `/mark` result). `AIMarking`
  validates that its verdict and suggested grade are what code derives from its coverage, so a client can't record
  one the AI didn't give. `marked_by: "ai"` needs `ai_marking` whose `suggested_grade` equals the grade (422
  otherwise); the student still presses it. A marking for other key points than the item has now (edited since, or a
  flashcard) is a 422.
- When the student saw a marking but chose another grade, the review is "self" and keeps the marking: the gap between
  the AI's suggestion and the student's choice stays measurable.
- **Migration 0027:** `reviews.ai_marking` (JSONB), with a check that `marked_by = 'ai'` comes with a marking. The
  append-only trigger stays.

### The tick list

"Show reference" shows the reference answer and its key points as a tick list; code suggests a grade from the ticks by
the same rule (all: Good; at least half: Hard; fewer: Again). The suggestion is outlined on its button and named in the
button's accessible name; it's never pressed for the student.

### The screens (`apps/web/src/features/practice/`)

- **/practice:** due now, new today (with the allowance left and the new cards waiting) and next due, from
  `GET /practice/queue`; Start review; a module filter; every topic's mastery weakest first (a band chip only when
  estimated, the basis sentence, item counts), with Generate practice (polled: queued, writing, then "8 written" or
  why not) and Add a card.
- **Review session (/practice/review?module=):** one item at a time from the queue, fetched again after every review,
  so a card in a learning step comes back when it's due; when nothing is due but a learning step is under 20 minutes
  away, the session waits for it (or the student finishes). A flashcard: the prompt, then Show answer (Space or Enter).
  A short answer: a textarea, then Check with AI (optional) or Show reference. Then Again, Hard, Good, Easy with their
  intervals from `/preview` (keys 1-4). `duration_ms` runs from showing the question to the grade. Sources are "CH05
  p14" chips that open the material at the page. The end shows the number reviewed, the share right (Good or Easy,
  measured, with its count) and the next due.
- **Items (/practice/items?module=&topic=):** filters (topic, status, origin, kind); each row's kind, origin (AI or
  Yours), memory state and due, and sources; edit, suspend or restore, reject an AI item with a reason, delete after
  a confirmation. A topic's list includes its subtopics (`subtopics=true`), as its mastery and counts do.
- **Settings → Practice:** new cards a day, desired retention ("Higher means more reviews and better recall").
- **Today:** a Reviews card ("4 due now · 12 new today", Start review), or "Next review in 3 h".
- **The topic dialog:** a Practice section with the topic's item count (linking to its items) and Generate practice.
- **Accessibility:** everything works by keyboard; focus moves to the new question, the revealed answer, the AI's check
  and the summary; results are announced in an aria-live region; every button has an accessible name. The review card is a
  solid surface (it's reading material).

### API additions

`GET /practice/items` gains `kind` and `subtopics` (with `topic_id`, the topic's whole subtree, by a recursive query
scoped to the user). `ReviewOut` gains `ai_marking`.

### Eval

`python -m evals.practice_marking cos330` (local, never in CI) writes 10 short-answer items on the fly from the topics
in `evals/practice/cos330.yaml` (nothing stored), gives each three answers with a known verdict (the reference itself:
correct; the first half of the key points, rounded up: partly; another topic's reference: incorrect), marks all 30
and writes agreement, numbers only, to `evals/results/practice-marking-cos330.json`. First run: **90.0 %** (27 of 30):
correct 70 % (7 of 10; 2 judged partly, 1 incorrect), partly 100 %, incorrect 100 %, none failed. All 30 were marked by
`groq/openai/gpt-oss-120b`. Every miss was the strict kind, never a lenient one: three
reference answers were judged not to state every key point. The eval keeps no text, so why isn't recorded; a likely
cause is generated key points that the reference answer doesn't state outright, which the generation filter could
check.

## Alternatives

- **The AI suggests the grade:** a model's grade is a number the student would take as fact; coverage per key point is
  something they can check line by line, and code turns it into a grade the same way every time.
- **Auto-submitting the AI's grade:** the student would stop judging their own answer, and an AI error would go
  straight into the schedule. The student always presses the grade.
- **Storing the marking separately from the review:** a second table for an object that only exists with its review.
- **A non-interactive marking that waits out rate limits:** the student is looking at the screen; a quick 503 with
  "mark it yourself" is better than a long spinner.

## Consequences

- AI marking can be audited later: every AI-marked review carries what the AI said and what the student chose.
- A topic's mastery doesn't change because of the AI: reviews (graded by the student) do.
- Task 5 (Quiz me and the planner using mastery) is unchanged by this.
