# 0003: Study sessions are an event log; totals are derived

- **Date:** 2026-11-13
- **Status:** Accepted

## Context

The study timer (Phase 1) and the insights built on it later (usual session length, break habits, productive times)
need durations the student can trust. A timer runs in a browser tab that can be reloaded, throttled, put to sleep or
taken offline. If the client reported "I studied 47 minutes", one lost or repeated request would corrupt the record
and nothing could be checked or rebuilt.

## Decision

- **Events are the source of truth.** The client posts timestamped events: `start`, `pause`, `resume`, `break_start`,
  `break_end`, `end`. It never sends durations. They're stored append-only in `session_events`.
- **One pure reducer** (`app/services/sessions/timeline.py`) replays a log into state and totals:
  - Active time and break time are counted separately. Paused time counts as neither.
  - Illegal transitions are rejected.
  - The totals and state on `study_sessions` are a cache rebuilt from the log on every write.
- **Totals run to the last event, never to "now".** Event times come from the client clock, so the server clock is
  never mixed in. A live timer adds `now − last_event_at` on its own clock.
- **Idempotent, offline-safe writes:**
  - Every event has a client-generated UUID.
  - A resent event with the same details is a no-op. The same id with different details is a 409.
  - Batches may arrive late and out of order. They're merged by `(occurred_at, seq)`, the whole log is re-validated,
    and the batch is saved all or nothing.
  - Starting a session is idempotent on the start event's id. The server generates the session id.
- **Event ids are unique per user** (PK `(user_id, id)`), so one user's ids can never collide with, and so reveal,
  another's.
- **At most one open session per user**, enforced by a partial unique index on `study_sessions (user_id) WHERE ended_at IS NULL`.
- **The reflection is separate from the log.** The session row holds focus 1–5 and what was covered.
  `session_topic_ratings` holds confidence 1–5 per topic, and only ended sessions accept a reflection.
  Reflections are personal data and never go into AI prompts (0002).

## Alternatives considered

| Option | Why not |
| --- | --- |
| Client sends running totals | One retry or lost request corrupts the record. It can't be audited or rebuilt. |
| Server timestamps the events on arrival | Offline replays and slow networks would shift every event to when it arrived |
| Totals computed to server "now" | Mixes two clocks; a skewed device clock would show negative or jumping time |
| Client-generated session ids | Simpler offline queue, but a global id collision would reveal another user's session |
| A strict per-session event sequence number | Breaks when two tabs or an offline replay interleave; time order plus server `seq` is enough |

## Consequences

- The timer (Phase 1 task 6) keeps a local queue of events and posts them in batches. It posts `start` first and uses
  the returned session id for the rest.
- Insights can recompute any session from its events, for example after a reducer bug fix.
- Event times are trusted within a 5-minute clock tolerance: an event too far in the future is rejected. A device whose
  clock jumps backwards mid-session can produce an invalid order, which is rejected rather than silently stored.
- Sessions left open (a closed laptop) stay open until the client ends them. Auto-closing is left for a later task.
