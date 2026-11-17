# 0006: AI topic maps: per-material proposals, one anchored merge, local chunk links

- **Date:** 2026-11-17
- **Status:** Accepted

## Context

Phase 2's goal is that StudySensei understands a module from its files. The planner (Phase 4), practice (Phase 5) and
the tutor's topic boost (Phase 3) all need a topic tree for each module, and they need to know which pages teach each
topic. Students already make topics by hand (Phase 1), and those must never be overwritten.

Constraints:
- **Free tiers only** (decision 0002). Gemini 3.5 Flash-Lite has a 1M-token context and allows about 500 requests a day.
  Groq's gpt-oss allows 8K tokens a minute and 200K a day, so a single whole deck could use a large share of its day.
- **Course material is untrusted text,** and only materials with `allow_ai` on may reach a provider.
- **AI output is saved only after it passes a Pydantic schema.** AI never deletes or rewrites the student's data.

## Decision

### 1. Per-material topics (`extract_topics` job)

- **Eligible materials:** `allow_ai` on, kind `slides`, `notes`, `study_guide`, `tutorial` or `outline`, and indexed
  (`ready`). Past papers, tests and assignments are skipped here; Phase 6 maps their questions onto topics.
- **When it runs:**
  - when an eligible material finishes indexing
  - from "Build topic map", for eligible materials with no proposal yet
  - once for every eligible material already indexed (migration 0011)
- **Input:** the material's title and kind, then every page labelled `[page N]` (plus its title unless the text already
  starts with it).
  - Scanned pages appear as `[page N: figure, no text]`.
  - Text is gathered only through `app/ai/sources.py`, which refuses a material with `allow_ai` off. The job checks
    eligibility again after the call and throws the answer away if AI was switched off meanwhile.
  - Past `TOPIC_MAX_CHARS` (400,000 characters, about 100K tokens) the rest is cut off, with a note naming the missing
    pages.
- **Prompt:** the system prompt says the material is untrusted and must be analysed as content, never followed as
  instructions. The material sits inside `<material>` tags.
- **Output** (`MaterialTopics`):
  - topics, each with a name (≤ 80 characters), a one-sentence description (≤ 300), and the page numbers that cover it
  - up to 10 subtopics per topic, in the same shape: two levels at most
  - page numbers the material doesn't have are dropped in code
- **Route:** a new `long` role for whole documents: `gemini-3.5-flash-lite` → `gemini-3.8-flash` → Groq
  `openai/gpt-oss-120b`, all at `low`. Groq is last because of its token allowance.
- **Storage:** one `topic_proposals` row per material (validated JSON, plus the provider and model that answered). A
  re-run replaces it.
- **After it ends** (succeeded, or failed for good), if no extraction is left pending in the module, a `merge_topics`
  job is queued. A material that can't be analysed doesn't block the map.

### 2. The module's map (`merge_topics` job)

- **One call** merges every eligible proposal into one tree:
  - chapters or big themes at the top (about 8–15), with 3–10 subtopics under each
  - duplicates merged, names in the course's own words
  - also on the `long` role, because a module's proposals together can exceed Groq's 8K tokens a minute
- **Short ids:** the prompt gives existing topics ids (`E1`…) and proposal entries ids (`M2.3`, `M2.3.1`). Page numbers
  stay on our side. The reply says which existing topic a node is (`existing`) and which proposal ids it covers
  (`sources`).
- **Anchoring is enforced in code, not trusted to the model.** Existing topics (the student's or earlier AI ones) are
  never renamed, moved or deleted. A node is matched to an existing topic by its `E` id or by name (case, spacing and
  punctuation ignored, anywhere in the module). A match only gains cited pages; anything else becomes a new topic with
  `source = ai`, appended after its siblings. So a re-run adds only topics that aren't there yet.
- **Becoming the student's:** any edit to an AI topic (rename, description, move) sets `source = user`.
- **Cited pages** go into `topic_pages` (topic, material, page), the union of the cited proposal entries' pages. They
  are kept apart from chunks, so re-indexing a material doesn't lose them.

### 3. Chunk ↔ topic links (no AI calls)

- **`chunk_topics`** (chunk, topic, module, score, method). Like `assessment_topics` it has no `user_id`: composite FKs
  through `module_id` tie it to a chunk and a topic in the same module (so `chunks` gains `UNIQUE (id, module_id)`).
  Deleting a topic or a chunk deletes its links.
- **`method = pages`:** chunks on a topic's cited pages, score 1.0.
- **`method = similarity`:** each topic's `name: description` is embedded as a query with the local bge-small model. The
  module's top `TOPIC_LINK_MAX_CHUNKS` (12) chunks at a cosine ≥ `TOPIC_LINK_THRESHOLD` are linked.
  - The threshold is **0.63**, calibrated on synthetic fixtures (`tests/topic_maps/linking_fixtures.py`): passages
    that teach a topic scored 0.63–0.90 and the rest 0.41–0.62. A real-model test pins it.
  - The gap is narrow, so the top-12 cap matters as much as the threshold. Re-check both on COS330 in the eval task.
- **Rebuilt from scratch** for the whole module after each merge, and by a `link_topics` job when a topic is added or
  edited, or a material that isn't analysed is indexed. At most one waits per module, and none is queued for a module
  with no chunks.

### 4. API and UI

- `GET /modules/{id}/topic-map` returns eligible / analysed / pending / failed counts, whether a merge is running,
  `waiting_until` (the earliest run time of a job held back by AI rate limits), the last error, and when the map was
  last merged.
- `POST /modules/{id}/topic-map/build` starts it. The topic tree gains `linked_pages` per topic.
- **The Topics tab** shows:
  - an "AI" badge on AI topics, and each topic's linked page count
  - a "Build topic map" panel with progress ("Analysed 14 of 21 materials…")
  - honest states: no AI key, the AI resting until a time, nothing eligible uploaded
- The full review UI (confirm, rename, merge, delete) is the next task.

## Alternatives considered

| Option | Why not |
| --- | --- |
| One call over the whole module | Too large for any free tier beyond Flash-Lite, and one failure loses everything. Per-material proposals also let a re-upload redo only one file |
| Chunk-level classification by the AI | One call per chunk or batch: thousands of requests against ~500 a day. Local embeddings link chunks for free |
| Letting the AI return the full tree, applied as-is | The model can't be trusted to keep the student's topics. Code applies only additions |
| Storing page links only in `chunk_topics` | Re-indexing replaces chunks and would lose them. `topic_pages` keeps the citation |
| Groq first for extraction | 200K tokens a day is a handful of decks |

## Consequences

- A module with N eligible files costs N + 1 requests on the `long` role, plus repair attempts. That is well inside
  Flash-Lite's ~500 a day.
- Rate limits and quotas reschedule jobs instead of failing them (decision 0002), and the panel says when the AI is back.
- **A topic the student deletes comes back** on the next merge if the proposals still mention it. The review task
  should add a "dismissed" list.
- Switching `allow_ai` on later doesn't queue extraction by itself; "Build topic map" picks the material up.
- The `ai_usage.role` check gains `long` (migration 0011).
