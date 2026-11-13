/**
 * Dates are stored as UTC ISO strings and shown in the browser's own timezone.
 * Forms work with separate local "YYYY-MM-DD" and "HH:MM" values.
 */

const pad = (n: number) => String(n).padStart(2, "0");

/** Local date ("2026-11-28") + time ("09:00") → UTC ISO string. */
export function toIso(date: string, time: string): string {
  return new Date(`${date}T${time || "00:00"}`).toISOString();
}

/** ISO string → the local date and time parts a form needs. */
export function fromIso(iso: string): { date: string; time: string } {
  const d = new Date(iso);
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

const dueFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** "Fri 28 Nov, 09:00" */
export function formatDue(iso: string): string {
  return dueFormat.format(new Date(iso));
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Whole calendar days from `now` to `iso` (negative = in the past). */
export function daysUntil(iso: string, now: Date = new Date()): number {
  return Math.round((startOfDay(new Date(iso)) - startOfDay(now)) / 86_400_000);
}

/** "today", "tomorrow", "in 12 days", "yesterday", "3 days ago". */
export function relativeDay(iso: string, now: Date = new Date()): string {
  const days = daysUntil(iso, now);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  return days > 0 ? `in ${days} days` : `${-days} days ago`;
}

export function isPast(iso: string, now: Date = new Date()): boolean {
  return new Date(iso).getTime() < now.getTime();
}
