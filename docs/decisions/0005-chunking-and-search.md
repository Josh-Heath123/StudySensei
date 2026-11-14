# 0005: Page-bound 400-token chunks, local bge-small embeddings, and exact hybrid search

- **Date:** 2026-11-14
- **Status:** Accepted

## Context

Phase 2 makes a module's materials searchable, and Phase 3's tutor will cite what search returns. Every result has to
point at one exact page or slide, so the student (and later the pdf.js viewer) can jump to it.

ARCHITECTURE.md planned chunks of "~400–800 tokens" and local embeddings with `BAAI/bge-small-en-v1.5` (384
dimensions, CPU, via fastembed). That model reads **at most 512 tokens**, including its `[CLS]` and `[SEP]` tokens, and
silently drops the rest. An 800-token chunk would be embedded from its first ~510 tokens only: the second half could
never be found by meaning, though keyword search would still match it.

The scale is one student: a module has tens of files and a few thousand chunks at most.

## Decision

- **Chunks never span two pages.** The chunker reads one `material_pages` row at a time. A chunk stores its page number
  and its position on the page.
- **At most 400 tokens per chunk, counted with the model's own tokenizer** (a copy of fastembed's tokenizer with
  truncation turned off, so long text is counted, not clipped). 400 leaves room for the heading below and the two special
  tokens inside 512.
  - A page that fits is one chunk.
  - A longer page is split at paragraphs (blank lines), then lines (slide bullets have no full stops), then sentences,
    then words, only as far down as each piece needs. Pieces are packed greedily up to 400 tokens.
  - Each chunk after the first starts with up to ~50 tokens from the end of the previous one, from a sentence start when
    one fits (words otherwise), so an idea cut at a boundary is still found.
  - A chunk is a slice of the page text, so its stored text is exactly as on the page.
- **The embedded text leads with context:** "material title · page title" (e.g. "CH03 · User authentication"), then a
  blank line and the chunk. Titles are cut to 150 characters, and dropped if they would push the input past 510 tokens.
  The stored text and the keyword index don't include them.
- **Scanned pages are skipped**; the vision step will fill them in later.
- **Storage:** a `chunks` table with user, module, material, page number, position, text, token count,
  `embedding vector(384)`, and a generated `tsv tsvector` (`to_tsvector('english', text)`) with a GIN index.
  - **Isolation:** composite FKs to `materials (id, user_id)` and `materials (id, module_id)`, as for other tables.
  - **Cascades:** an FK to `material_pages (material_id, page_number)` with `ON DELETE CASCADE`, so re-extracting a
    material (which replaces its pages) removes its chunks, and deleting a material deletes them too.
- **Pipeline:** a successful `extract_text` queues `index_material` in the same transaction. The material stays
  `processing` until indexing finishes and only then becomes `ready`, so "Ready" means searchable. Re-indexing replaces the
  material's chunks. Migration 0007 queues indexing for materials already extracted.
- **Embedding:** fastembed with `passage_embed` for chunks and `query_embed` for searches (bge's query instruction),
  batches of 32. The model is loaded once per process (worker or API) on first use, and cached in `data/models`
  (gitignored); the first run downloads it (~65 MB) and logs that it is doing so. Embedding is local, so it runs whatever
  `allow_ai` says; that switch only matters once text goes to Gemini.
- **Search:** `GET /modules/{id}/search?q=&limit=8`.
  - **Vector:** the 20 nearest chunks by cosine distance, an **exact scan** of the module's chunks (filtered by user and
    module through `ix_chunks_user_module`).
  - **Keyword:** the 20 best `websearch_to_tsquery('english', q)` matches, ranked by `ts_rank_cd`.
  - **Fusion:** reciprocal rank fusion, score = Σ 1 / (60 + rank).
  - **Snippets** come from `ts_headline`, marked with two Unicode interlinear-annotation characters and split into
    plain/highlighted parts, so no HTML ever reaches the browser.
- **Tests** embed with a deterministic fake (hashed bag of words), so CI never needs the model. One smoke test uses the
  real model on the fixture files; CI caches `data/models`.

## When to add a vector index

No HNSW index for now. An exact scan never misses a result, needs no tuning, and at one student's scale (a few thousand
384-dimension vectors per module) it takes milliseconds. pgvector's HNSW is approximate, and with a `WHERE user_id AND
module_id` filter it can return fewer than 20 rows unless `ef_search` is raised or iterative scans are used.

Add HNSW (`vector_cosine_ops`) when a single module's scan regularly costs more than ~50 ms, which is around 50–100k chunks
in one module, or once many users share one database (Phase 9) and a scan per search shows up in the database's load.

## Alternatives

- **400–800-token chunks:** the model truncates at 512, so anything beyond is invisible to vector search.
- **Chunks across page boundaries:** slightly better context at the joins, but a result could no longer cite one page.
  The overlap covers ideas cut mid-page; ideas cut across pages are rare in slides.
- **Counting tokens by words or characters:** cheap, but wrong by 20–50 % on code, maths and acronyms, which is exactly
  what overruns the limit.
- **A larger model (bge-base, 768 dims) or a hosted embedding API:** better recall, but 3–4× slower on a laptop CPU, or
  course text leaves the machine.
- **Fusion in SQL:** possible, but RRF is a few lines of pure Python that are easy to test.
- **Returning `ts_headline` HTML (`<b>…</b>`):** simple, but rendering it means trusting markup built from course text.

## Consequences

- Materials take longer to become "Ready": extraction, then embedding (a few seconds per hundred chunks on a CPU).
- The worker and the API each hold the model in memory (~100 MB) once it's first used. The API loads it on the first
  search, so that search is slower.
- Chunk sizes are tied to this model's tokenizer. Changing the model means a new decision, a migration for the vector
  size, and re-indexing every material (queue `index_material` for each).
- `chunk_topics` (topic linking) and the current-topic boost build on these chunks in later Phase 2 and Phase 3 tasks.
