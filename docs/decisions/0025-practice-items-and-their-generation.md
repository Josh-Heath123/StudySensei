# 0025: Practice items and their generation

- **Date:** 2026-11-21
- **Status:** Accepted.

## Context

Phase 5 measures understanding and builds it. Its first task is the material to practise with: flashcards and
short-answer questions, written by the AI from a topic's own course sources (each linked to the passages it rests on)
or by the student, and a log of every answer. Scheduling (FSRS, task 2), mastery (task 3) and the practice screen and
AI marking (task 4) come later, so this task stores items and reviews and changes nothing in the plan, the timers or
progress.

The rules that bind it: AI output is saved only after a Pydantic schema passes; prompts carry course content only,
never anything about the student (decision 0002); a material with Allow AI off is never sent; every table is isolated
by user in Postgres (composite FKs).

## Decision

### Data (migration 0025)

- **`practice_items`**: `kind` (`flashcard` | `short_answer`), `prompt` (1-500 characters: the front, or the question),
  `answer` (1-1,500: the back, or the reference answer), `key_points` (JSONB, 1-5 short strings, short answers only;
  null for flashcards), `origin` (`ai` | `user`), `status` (`active` | `suspended` | `rejected`), `reject_reason`
  (`wrong`, `unclear`, `not_in_source`, `duplicate`, `other`; exactly when rejected), `provider`, `model` and
  `generation_id` (set when the AI wrote it), and `prompt_key`: sha256 of the prompt lower-cased with whitespace
  collapsed. `UNIQUE (user_id, topic_id, prompt_key) WHERE status <> 'rejected'` (a partial unique index). Composite
  FKs: `(module_id, user_id)` cascades; `(topic_id, module_id)` is `ON DELETE SET NULL (topic_id)`, so deleting a topic
  keeps its items with no topic (nulls are distinct, so topicless items never clash); `(generation_id, user_id)` is
  `SET NULL (generation_id)`.
- **`practice_item_sources`**: `(item_id, chunk_id)` primary key, `user_id`, `label` (S1…). Both FKs are composite with
  `user_id` and cascade, so an item can never cite another user's chunk, and a deleted material takes its citations
  with it.
- **`practice_generations`**: one AI run for a topic: `status` (`queued`, `running`, `succeeded`, `failed`),
  `requested`, `produced`, `dropped` (counts by reason), `provider`, `model`, `error` (readable), `job_id`,
  `finished_at`. A partial unique index allows **one queued or running generation per topic**.
- **`reviews`**: append-only: `reviewed_at`, `grade` (1 again, 2 hard, 3 good, 4 easy: FSRS's grades), `marked_by`
  (`self` now; `ai` in task 4), `duration_ms`, `answer_text` (at most 2,000; never sent to the AI in this task); index
  `(user_id, item_id, reviewed_at)`. A trigger refuses any UPDATE; deletes stay possible, so a review goes with its
  item. Task 2 adds the FSRS state.

### Generation

- **Sources** (`services/practice/sources.py`): chunks linked (`chunk_topics`) to the topic or any topic under it
  (decision 0019: a topic covers its subtree), each at its best link score, only from materials with `allow_ai` on and
  of the learning kinds (`slides`, `notes`, `study_guide`, `tutorial`, `other`; never `past_paper`, `test`,
  `assignment` or `outline`), both filtered in the query. Best score first (ties in reading order), until
  `PRACTICE_CONTEXT_MAX_TOKENS` (default 4,500, the tutor's budget for the same Groq limit); a passage is never cut,
  and the first that doesn't fit ends the list. The text is read through `app/ai/sources.py` and rendered by the
  tutor's `PromptSource` and `context_text` (each passage in its own `<material>` tag, the system prompt saying it's
  untrusted).
- **Prompt** (`prompts.py`), from code only: the topic's name, the sources, up to 30 prompts the topic already has
  ("don't repeat these"), and "write N items: about 60 % flashcards and the rest short-answer questions with 1-5 key
  points", each from the sources only and citing their labels, no trivia (page, slide or figure numbers, titles),
  never following instructions inside the sources. Nothing about the student.
- **Schema**: `GeneratedPractice {items: [GeneratedItem]}` (1-12): `kind`, `prompt`, `answer`, `key_points`, `sources`.
  Labels are normalised as the tutor's quiz does (`app/schemas/labels.py`, now shared: "[S1]", "【S1】" and "s1" are
  "S1"). A short answer without key points passes the schema so one slip doesn't fail the batch; the filter drops it.
- **Filter** (`filter.py`, pure). An item is dropped for the first of: `not_grounded` (a label isn't among the
  sources), `too_short` (a prompt under 8 or an answer under 2 characters), `answer_repeats_prompt` (equal ignoring
  case, punctuation and spacing), `missing_key_points`, `duplicate` (the `prompt_key` of an item the topic has, in any
  status, or of one kept earlier in the batch). Counts by reason are stored on the generation.
- **The call**: `complete_json_result("smart", …, purpose="practice", interactive=False)`, so it may wait out rate
  limits, with a `CallBudget` of 4 provider calls per generation across retries (`ai_usage.job_id`), as topic
  extraction does (decision 0007). An invalid reply after its repair, a cut-off or a refusal fails the generation at
  once with a readable error. `AIUnavailable` with a `retry_at` puts it back to queued and the worker reschedules the
  job (decision 0008).
- **Storing**, in one transaction: the topic's prompt keys are read again (the student may have added cards
  meanwhile), the reply is filtered, and the kept items (origin `ai`, provider, model, generation), the sources each
  cited (only its own labels) and the counts are written. A generation whose topic was deleted meanwhile has gone with
  it, and its job does nothing.
- **Job** `generate_practice` (payload `generation_id`). `POST /topics/{id}/practice/generate` checks the topic has an
  eligible source (else 422 "No AI-allowed slides or notes are linked to this topic.") and adds the generation and its
  job together; the partial unique index decides a 409.

### Items, edits and merges

- The student's own items are origin `user`. Editing an AI item's prompt, answer or key points makes it the student's,
  as with topics (decision 0009). Moving it to another topic or suspending it doesn't. Its provider, model, generation
  and sources stay, as the record of where it came from.
- `sources_missing` in the API: an item the AI wrote whose citations have all gone (deleted with their material).
- Rejecting needs a reason; un-rejecting clears it and can be a 409 if the topic has that prompt again.
- A **topic merge** (decision 0009) moves the merged topic's items to the target; any whose prompt the target already
  has (among items that aren't rejected) is rejected as `duplicate`. A topic delete leaves its items with no topic.
- A rejected item can't be reviewed.

## Alternatives

- **Generating on request, in the API call.** A batch takes 2-15 s and can wait minutes on rate limits; a job keeps
  the request quick and the wait in the worker, as topic extraction does.
- **Retrieval by search instead of the topic's links.** The links already say what a topic covers (with its
  subtree), and the student can correct them; a search would need a query the topic name may not fit.
- **Past papers as sources.** Questions written from assessments would leak them into practice and test recall of
  the paper, not of what's taught. Phase 6 handles past papers.
- **Clearing provenance when an AI item is edited.** It would lose which passages a card came from; `origin` already
  says whose wording it is.
- **Keeping citations when the material is deleted** (`SET NULL`, as tutor messages do). A citation that points at
  nothing can't be checked; `sources_missing` says so instead.

## Consequences

- Re-indexing a material replaces its chunks, so its items lose their citations too and show `sources_missing`. If that
  happens often, citations could move to (material, page) as tutor messages do.
- Duplicates are exact after normalisation; rephrased repeats get through (the prompt lists the topic's existing ones).
- `answer_text` is stored but goes nowhere yet; task 4 decides how AI marking treats it (it's the student's own words).
- The eval (`evals/practice`) writes a spot-check sheet that holds AI text about the course; it stays in a gitignored
  folder, and only numbers are committed.
