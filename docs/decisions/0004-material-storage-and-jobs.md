# 0004: Materials are stored by content hash; background work runs from a Postgres job queue

- **Date:** 2026-11-13
- **Status:** Accepted

## Context

Phase 2 turns uploaded course files into text, chunks, embeddings and topic maps. That needs two things:
- somewhere to keep the files
- a way to process them outside the request, surviving restarts and failures

Students re-upload the same slides often, sometimes to several modules. Course material is personal data, and other people's
work is never shared between accounts. The app runs locally on one machine today, with only Postgres as infrastructure
(decision 0001).

## Decision

- **Storage interface.** `app/storage/base.py` defines `Storage` (`put`, `open`, `exists`, `path_for`, `delete`).
  - `LocalStorage` keeps files under `data/materials` (gitignored), writing atomically (temp file, then rename).
  - A cloud implementation can replace it later without touching callers.
- **Keyed by `{user_id}/{sha256}`.** Keys are validated against that exact shape, so no key can point outside the
  storage root.
  - **Dedupe:**
    - the same file twice in one module is a 409 that names the existing material (`UNIQUE (module_id, sha256)`)
    - the same file in another of the user's modules gets its own row but shares the blob
  - **Deletion:** a blob is deleted only when the user's last material using it is deleted, including when a module is
    deleted.
  - **No sharing:** nothing is shared across users, even for identical files.
- **Uploads are checked by content.** The extension must be on the allow-list (PDF, PPTX, DOCX, MD, TXT, PNG, JPG), and
  the bytes must match it:
  - PDF: the `%PDF-` header
  - PPTX/DOCX: an OOXML zip layout
  - PNG/JPEG: their signatures
  - MD/TXT: UTF-8 with no NUL bytes

  The limit is 50 MB: checked from `Content-Length` first, then counted while hashing.
- **Jobs live in Postgres.** The `jobs` table holds kind, payload, `user_id`, status, attempts, `run_after`, `locked_at`
  and `last_error`.
  - **Enqueueing** happens in the same transaction as the change that needs the job, so a material and its job exist
    together or not at all.
  - **Claiming:** the worker (`app/jobs/worker.py`, started by `npm run dev`) takes the next due job with
    `FOR UPDATE SKIP LOCKED`, so several workers can run safely. It also takes back jobs locked for more than 10 minutes,
    because their worker died.
  - **Retries:** a failure is retried after 30 s, 2 min and 8 min (capped at 30 min), up to `max_attempts` (3). Expected
    failures (`JobError`) carry a message safe to show; anything else shows a generic one and is logged.
  - **User scoping:** jobs carry `user_id`, and handlers scope every query by it.
- **`allow_ai` on each material** (default on) is the student's switch. AI jobs must skip materials where it's off. The
  page count isn't AI and ignores it.

## Alternatives

- **Store by material id instead of by hash:** simpler deletes, but the same file is stored once per upload, and nothing detects duplicates.
- **Global hash keys (shared across users):** less disk, but one user's upload would reveal that another has the same file,
  and deleting needs cross-user reference counts.
- **Redis/RQ, Celery or Dramatiq:** mature, but they add a service to run and back up. A Postgres queue is plenty at one
  user's scale and keeps jobs transactional with the data.
- **`LISTEN/NOTIFY` instead of polling:** lower latency. Polling every second is simpler and good enough; it can be added
  later without changing the table.

## Consequences

- `npm run dev` runs three processes: API, worker and web. Material processing stops when the worker isn't running, and
  the UI shows "Waiting to be processed…".
- Deleting files is the application's job: the database cascade removes rows, not files. Module and material deletes
  clean up their blobs.
- Two concurrent requests could race between a blob delete and an upload of the same file. The upload always rewrites
  the blob, which makes this unlikely for one user. A periodic orphan sweep can close the gap if it ever matters.
- Every later Phase 2 step (extraction, chunking, embedding, topic extraction) is a new job kind in `HANDLERS`.
