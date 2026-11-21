/**
 * The week view's pure helpers: local dates and minutes in the user's timezone (not the
 * browser's), the Monday-first week, and where a block or a free window sits on the grid.
 * No planning rules live here: what can move, be skipped or started comes from the API.
 */

/** "YYYY-MM-DD" and minutes after local midnight, in `timeZone`. */
export type Zoned = { date: string; minutes: number };

const formatters = new Map<string, Intl.DateTimeFormat>();

function partsFormatter(timeZone: string): Intl.DateTimeFormat {
  let found = formatters.get(timeZone);
  if (!found) {
    found = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    formatters.set(timeZone, found);
  }
  return found;
}

/** An instant as a local date and minute in `timeZone`. */
export function zoned(at: string | number | Date, timeZone: string): Zoned {
  const parts = Object.fromEntries(
    partsFormatter(timeZone)
      .formatToParts(new Date(at))
      .map((p) => [p.type, p.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

/** The UTC instant of `minutes` after local midnight on `date` in `timeZone`. */
export function fromZoned(date: string, minutes: number, timeZone: string): Date {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  const wall = Date.UTC(y, m - 1, d, 0, minutes);
  // The zone's offset at that wall time, found by looking at what the guess shows there.
  let guess = wall;
  for (let i = 0; i < 2; i++) {
    const shown = zoned(guess, timeZone);
    const [sy, sm, sd] = shown.date.split("-").map(Number) as [number, number, number];
    const shownWall = Date.UTC(sy, sm - 1, sd, 0, shown.minutes);
    guess += wall - shownWall;
  }
  return new Date(guess);
}

/** `date` plus `days` (calendar arithmetic on "YYYY-MM-DD"). */
export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** 0 for Monday … 6 for Sunday. */
export function weekday(date: string): number {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

/** The Monday of `date`'s week. */
export function mondayOf(date: string): string {
  return addDays(date, -weekday(date));
}

/** The seven dates of the week starting `monday`. */
export function weekDates(monday: string): string[] {
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Tue 24 Nov". */
export function dayLabel(date: string): string {
  const [, m, d] = date.split("-").map(Number) as [number, number, number];
  return `${DAYS[weekday(date)]} ${d} ${MONTHS[m - 1]}`;
}

/** "18:05". */
export function clock(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** A stretch on one local day, in minutes after midnight. */
export type Span = { date: string; start: number; end: number };

/** An interval as spans per local day (a window never crosses midnight, but be safe). */
export function toSpans(start: string, end: string, timeZone: string): Span[] {
  const a = zoned(start, timeZone);
  const b = zoned(end, timeZone);
  if (a.date === b.date) return [{ date: a.date, start: a.minutes, end: b.minutes }];
  return [
    { date: a.date, start: a.minutes, end: 24 * 60 },
    { date: b.date, start: 0, end: b.minutes },
  ];
}

/**
 * The grid's hour range: from the earliest free window or block of the week (floored to
 * the hour) to the latest (ceiled), never the whole day by default. `null` with nothing.
 */
export function hourRange(spans: Span[]): { first: number; last: number } | null {
  if (spans.length === 0) return null;
  const first = Math.floor(Math.min(...spans.map((s) => s.start)) / 60);
  const last = Math.ceil(Math.max(...spans.map((s) => s.end)) / 60);
  return { first, last: Math.max(last, first + 1) };
}

/** Snap minutes to the 5-minute grid. */
export function snap5(minutes: number): number {
  return Math.round(minutes / 5) * 5;
}

/** 5-minute starts for a block of `length` minutes inside a day's free spans. */
export function startsWithin(spans: Span[], length: number): number[] {
  const out: number[] = [];
  for (const span of spans) {
    for (let t = Math.ceil(span.start / 5) * 5; t + length <= span.end; t += 5) out.push(t);
  }
  return out;
}

/** A done card is at least this tall, so a very short session is still a card you can see and
 * click (a 4-second one was a 14 px sliver under the next card). */
export const MIN_DONE_CARD_PX = 24;

/** A grid card's height: its minutes at ``pxPerMinute``; at least MIN_DONE_CARD_PX if done. */
export function cardHeight(
  block: { minutes: number; status: string },
  pxPerMinute: number,
): number {
  const height = block.minutes * pxPerMinute;
  return block.status === "done" ? Math.max(MIN_DONE_CARD_PX, height) : height;
}
