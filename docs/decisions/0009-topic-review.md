# 0009: Topic review, the student's edits win, and a merge Groq can take

- **Date:** 2026-11-17
- **Status:** Accepted. Builds on 0006 (topic maps), 0007 and 0008 (bounded calls).

## Context

- **The review step:** COS330's topic map rebuilt into 53 AI topics. Phase 2 needs the student to review them, and its
  roadmap check is that at least 80 % of proposed topics are kept with small edits. That needs the outcomes recorded,
  not guessed.
- **The merge had no fallback:**
  - One evening Gemini answered the merge with 503s and 3.8 Flash's daily budget was used up.
  - Groq refused it as "request too large" (413): its free tier allows 8K tokens a minute, and the merge prompt was
    about 15–18K tokens (Gemini counted 14,907 and 17,655), because it carried every proposal's description.
  - Each 413 also counted toward the 4-call cap.
- **Relinking undid fixes:** chunk links are rebuilt from scratch, so any fix a student made to them was lost the next
  time topics changed. The student's edits have to survive that.

## Decision

1. **A compact merge input** (`merge_messages`, `TOPIC_MERGE_MAX_TOKENS` = 7000):
   - Each proposal is `M3.2 Firewalls (4 p)`: its id, its name and how many pages it cites.
   - Descriptions are added, top-level proposals first, only while the whole request still fits. "The whole request"
     means the system prompt, the JSON instruction the client adds and the prompt. Tokens are estimated at 3.5
     characters each, which is cautious: the COS330 prompt was 68,720 characters for 14,907 Gemini tokens, 4.6 each.
   - On COS330 (460 proposals) the input is 24.8K characters without descriptions, against 68.7K with them. That's
     about 5.4K tokens, which fits Groq.
   - If even the names don't fit, the request goes out anyway: Gemini takes it, and Groq's 413 moves on.
2. **A 413 is "turned away", like a 429 or 503:**
   - It's logged as the new outcome `too_large`.
   - It doesn't count toward the call cap or the daily budget; it counts toward `TOPIC_MAX_TURNED_AWAY`.
   - The model isn't cooled down, because a smaller request may well fit.
3. **Review actions** on each AI topic:
   - **Keep:** confirms it as it is.
   - **Rename:** inline, through the usual PATCH. It counts as renamed if the name changed (case and punctuation
     ignored). A description edit or a move counts as kept.
   - **Merge into:**
     - The topic's subtopics, cited pages (`topic_pages`) and current chunk links move to the chosen topic, then it's
       deleted.
     - Not into itself or one of its own subtopics, and not across modules (422).
     - The target, chosen as its home, counts as kept if it was AI.
     - Moved similarity links last until the next relink, which links the target by its own name and description;
       cited pages stay.
   - **Dismiss:**
     - The topic is deleted, and so are its subtopics still marked AI. The student's own (or already reviewed)
       subtopics move up to its parent.
     - Only a topic still marked AI can be dismissed; others are deleted the ordinary way.
   - **Keep all remaining:** keeps every topic still marked AI, behind a confirm.
   - Every action makes the topic the student's (`source = user`), as edits already did.
4. **`topic_reviews`: one row per AI topic, written on the first action:**
   - The row stores the AI's name and its `name_key`, the outcome (`kept`, `renamed`, `merged`, `dismissed`) and
     `target_id`, the topic now carrying that name.
   - A later action updates the row. A kept topic later renamed counts as renamed; "kept" never downgrades
     "renamed".
   - The row outlives the topic. `target_id` is a single-column FK with `ON DELETE SET NULL`, because a composite one
     would null `module_id` too. `topic_id` has no FK.
   - A dismissed row also holds a snapshot (description, parent, cited pages) for Restore.
5. **The student's review wins in the merge:**
   - A name the student dismissed is never added again, and neither is anything the AI put under it.
   - The AI's original name for a renamed or merged-away topic adds cited pages to the topic that carries it now,
     instead of creating a duplicate.
   - **Restore** recreates a dismissed topic as the student's: its name, description and cited pages, under its old
     parent if that's still there (else at the top level). It then counts as kept, so its name is no longer blocked.
6. **Linked pages and unlinks:**
   - `GET /topics/{id}/pages` lists a topic's pages by material, each with its label (the page title, or its first
     line) and how it was linked: `pages` (cited) or `similarity` with the best chunk's score.
   - Unlinking a page records it in `topic_unlinks` and removes the cited page and the chunk links. Relinking skips
     unlinked pages for that topic, by both methods.
7. **Stats:**
   - `GET /modules/{id}/topic-map` gains `review`: kept, renamed, merged and dismissed (from `topic_reviews`), and
     unreviewed (topics still marked AI).
   - The Topics tab shows "N of M reviewed" and "Review: 40 kept, 6 renamed, 3 merged, 2 dismissed".
   - **The 80 % check** is (kept + renamed) ÷ (all reviewed).
8. **UI (Topics tab):**
   - **Topic row:**
     - AI topics show Keep, Merge into and Dismiss in place of Delete.
     - Dismissing a topic with AI subtopics asks first.
     - Clicking a topic's name opens its linked pages; Rename moved to the pencil button.
   - **Review filter:** shows only AI topics and the topics holding them. Moves are off while it's on, because the tree
     is cut down.
   - **Dismissed topics:** a collapsible list, fetched when opened, with Restore.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Drop subtopics from the merge input to fit Groq | The merge needs them to place and dedupe; names are cheap, descriptions aren't |
| Count tokens with a tokenizer | Each provider has its own; a cautious estimate is enough for a budget |
| Dismiss leaves AI subtopics in place (moved up) | Dismissing a junk chapter would scatter its junk subtopics across the tree |
| Block dismissed names in the prompt instead of in code | Costs tokens and the AI may still return them; the code check is certain |
| Store unlinks by chunk | Chunks are rebuilt when a material is re-indexed; pages are stable |
| Make unlinked pages a relink-time filter only | The page would stay linked until the next relink; deleting the links at once is clearer |

## Consequences

- Groq can step in for the merge when Gemini is busy or out of quota, at the cost of fewer descriptions.
- Every AI topic's fate is recorded, so the 80 % check can be read from the tab.
- A topic the student renamed, merged or dismissed stays that way when the map is rebuilt, and so do unlinked pages.
- Clear AI topics (0007) deletes only unreviewed AI topics and leaves `topic_reviews` alone, so a rebuild still
  respects dismissals.
