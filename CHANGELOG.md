# Changelog

One entry per roadmap phase of the web rebuild, newest first, from `docs/ROADMAP.md` and `docs/PROGRESS.md`. Each lists
the pull requests merged for it. The PyQt prototype before the rebuild is archived at the tag `v0-pyqt-prototype`.

## Phase 2: Materials and topic maps (13–18 Nov 2026, PRs #12–#28)

StudySensei understands a module from its files.

- Uploads with content-hash storage, type checks and a 50 MB limit, and a Postgres job queue with a worker (#12).
- Text extraction from PDF, PPTX and DOCX per page, with scanned pages flagged (#13).
- Page-bound chunks, local embeddings (bge-small-en-v1.5) and hybrid search (#14).
- One LLM client for Gemini and Groq free tiers: roles, daily budgets, pacing, timeouts, thinking levels and usage
  logging (#15–#18).
- AI topic maps: per-material proposals, an anchored merge and local chunk links, with bounded calls and handling for
  busy models and refusals (#19–#21, #23).
- Topic review: keep, rename, merge, dismiss and unlink, with the student's edits always winning (#22).
- A pdf.js materials viewer that opens at the right page (#24).
- An AI provider settings page with a key test (#25).
- Near-empty pages no longer link to topics by similarity (#26).
- A docs PR: the handover snapshot, the COS330 review and ADR 0011 (#27).
- Evals for search, linking and topic extraction against COS330 (#28). Search: an acceptable page in the top 3 for
  15 of 15 queries, a slide for 11 of 15 (the roadmap asks for 12). Topic review: 53 of 53 AI topics kept.

## Phase 1: Modules, assessments and study sessions (12–13 Nov 2026, PRs #2–#11)

A tool to use every day, before any AI.

- Modules, a topic tree, assessments and tasks, isolated per user in Postgres (#2–#5).
- The Today page with upcoming deadlines (#6).
- Study sessions as an append-only event log, and a timestamp-based timer engine with an offline queue (#7, #8).
- Design system v1, direction B "Planner" (#9).
- The session screen with breaks and a 20-second reflection, and session history per module (#10, #11).

## Phase 0: Reset and foundations (12 Nov 2026, PR #1)

A clean repository and a running skeleton.

- The PyQt prototype archived at `v0-pyqt-prototype` and its code removed.
- Postgres with pgvector in Docker, a FastAPI API and a Vite React shell, the typed API client, `npm run dev` and
  `npm run check`, CI, the Stop hook, and the first docs and ADRs (0001, 0002).
