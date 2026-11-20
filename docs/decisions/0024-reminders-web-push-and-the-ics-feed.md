# 0024: Reminders: Web Push and the ICS feed

- **Date:** 2026-11-22
- **Status:** Accepted.

## Context

Phase 4's last task: a reminder before each planned block on the devices the student chooses, and the plan in their
calendar app. There's no AI anywhere in this, and the web app decides nothing about the plan: the server chooses
which blocks get a reminder and what the calendar holds.

## Decision

### Web Push

- **Standard Web Push** (RFC 8030) with VAPID (RFC 8292), payloads encrypted end to end (RFC 8291, aes128gcm), sent
  from the worker with `pywebpush` (MPL-2.0; with `py-vapid` and `http-ece`, MPL-2.0). It sits behind a small
  `PushSender` protocol; tests use `FakePushSender` and never reach the network.
- **Keys:** `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT` (a `mailto:`) in `apps/api/.env`.
  `python -m app.push.keys` prints a new pair as three lines to paste; it never writes a file. Without all three,
  push is **disabled**, not an error: `GET /push/config` says so and nothing is queued.
- **Subscriptions** (`push_subscriptions`): endpoint (https only), `p256dh`, `auth`, a label from the user agent ("Edge
  on Windows"), `last_success_at`, `failures`; `UNIQUE (user_id, endpoint)`. Saving upserts by endpoint. The endpoint
  is a capability, so it's never returned or logged; logs name the subscription's id.
- **Outcomes of a send:** success sets `last_success_at` and `failures = 0`; 404 or 410 deletes the subscription; any
  other failure adds one, and the fifth in a row deletes it.
- **Which blocks:** once a minute the worker runs `queue_reminders(session, now)`: for each user with
  `reminder_minutes` set (5, 10, 15 or 30; null is off; default 10) and at least one subscription, the current
  version's planned blocks starting in (now, now + lead], with no linked session. Each gets a `reminders_sent` row
  (`ON CONFLICT DO NOTHING`) and a one-attempt `push_reminder` job in the same transaction; the job sends to every
  device of the user.
- **One per slot:** `reminders_sent` is keyed by the slot, `sha256(start, end, assessment, topic)`, not the block's id:
  every plan version gives blocks new ids, so a block carried forward unchanged as a fixed copy isn't reminded twice,
  and one that moved or was placed again is a new slot with its own reminder.
- **Payload:** `{title, body, url, tag}`: "Ch1 Overview at 18:00" (or "Final review: COS330 Exam at 18:00"), "50 min ·
  " and the method, "/", and the slot as the tag (a repeat replaces the earlier notification). Its TTL is the time
  left until the block starts (at most the lead), so a late one is dropped rather than shown after the start. A topic
  or assessment name and a time, nothing else: no reflections or notes.
- **The browser:** `public/sw.js` handles `push` and `notificationclick` only (no fetch handler, no caching). It's
  registered from `src/lib/push.ts` only when the student turns reminders on; permission is asked inside that click.

### The calendar

- **A private link:** `POST /calendar/feed` makes a token (32 random bytes, urlsafe), stores only its sha256 in
  `calendar_feeds` (one per user), and returns the URL once. Posting again resets it, and the old link stops working.
  `GET /calendar/feed` says whether it exists and when it was made and last fetched, never the token.
- **`GET /calendar/{token}.ics` has no session:** the token is the credential, looked up by its hash, and it serves only
  that user's plan; an unknown token is a 404. **This route must stay outside any future auth middleware** (Phase 9):
  calendar apps can't sign in. `GET /calendar/plan.ics` serves the same file to the signed-in user, for Download.
- **The file** (`services/calendar/ics.py`, pure, with `icalendar`, BSD-2-Clause): the current version's planned blocks
  that haven't ended, up to 8 weeks ahead, plus done blocks of the last 7 days at their measured time (0023) marked
  "✓ ". UID: the slot `@studysensei`, so an unchanged block keeps its UID across versions and a moved one is replaced.
  SUMMARY "Ch1 Overview · COS330" or "Final review · COS330 Exam"; DESCRIPTION "How: …\nWhy: …"; times in UTC;
  `X-WR-CALNAME`, `REFRESH-INTERVAL` and `X-PUBLISHED-TTL` of an hour. Served as `text/calendar; charset=utf-8` with
  `Cache-Control: private, max-age=300`.
- **Until StudySensei is hosted,** a calendar app can't reach a link on localhost; Settings says so and offers the file.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A third-party push service (Firebase, OneSignal) | An account, an SDK and their servers in the path; standard Web Push needs none |
| Key reminders by block id | Every re-plan makes new ids: a carried block would be reminded again each version |
| Send from the API on a timer | The worker already wakes every minute for nightly re-plans and owns retries |
| Retry a failed reminder job | It would resend to the devices that already got it; per-device failures are counted instead |
| Store the calendar token | A leaked database would leak every feed; a hash is enough to look it up |
| A fetch handler and offline caching in the service worker | Out of scope; a push-only worker can't break page loads |

## Consequences

- Reminders arrive on each device the student turned them on for, one per block, and stop for a device the push
  service says is gone.
- The plan can be downloaded as a file now, and subscribed to once the app is hosted.
- Three new user-owned tables and `users.reminder_minutes` (migration 0024).
