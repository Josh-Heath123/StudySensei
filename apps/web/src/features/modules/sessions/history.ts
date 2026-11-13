import type { components } from "@/lib/api/schema";

type Event = components["schemas"]["EventOut"];
type State = components["schemas"]["SessionOut"]["state"];

/** Monday 00:00 local time of the week `now` is in (the summary's "this week"). */
export function startOfWeek(now: Date): Date {
  const daysSinceMonday = (now.getDay() + 6) % 7;
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysSinceMonday);
}

/**
 * Active seconds as of `now`. The server's total runs up to the last event; an
 * active session adds the time since then (never negative if the clock is behind).
 */
export function activeSecondsAt(
  session: { state: State; active_seconds: number; last_event_at: string },
  now: number,
): number {
  if (session.state !== "active") return session.active_seconds;
  return session.active_seconds + Math.max(0, (now - Date.parse(session.last_event_at)) / 1000);
}

const LABELS: Record<Event["type"], string> = {
  start: "Started",
  pause: "Paused",
  resume: "Resumed",
  break_start: "Break started",
  break_end: "Break ended",
  end: "Ended",
};

export type TimelineRow = { id: string; label: string; at: string };

/** The session's events as rows for its timeline (they arrive in timeline order). */
export function timelineRows(events: readonly Event[]): TimelineRow[] {
  return events.map((event) => ({
    id: event.id,
    label: LABELS[event.type],
    at: event.occurred_at,
  }));
}
