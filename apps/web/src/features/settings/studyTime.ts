/** Pure helpers for Settings → Study time. Times are "HH:MM", and "24:00" ends a window at
 * midnight (an `<input type="time">` shows it as 00:00). */

export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

export type Clock = { start: string; end: string };

export function toMinutes(clock: string): number {
  const [hours = "0", minutes = "0"] = clock.split(":");
  return Number(hours) * 60 + Number(minutes);
}

export function fromMinutes(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

/** What a time input shows: "24:00" is midnight, 00:00. */
export function toInput(clock: string): string {
  return clock === "24:00" ? "00:00" : clock;
}

/** What the API gets from a time input: an end of 00:00 is the next midnight, "24:00". */
export function fromInput(value: string, isEnd: boolean): string {
  return isEnd && value === "00:00" ? "24:00" : value;
}

/** A window's length in minutes (0 if it's empty or backwards). */
export function windowLength({ start, end }: Clock): number {
  return Math.max(0, toMinutes(end) - toMinutes(start));
}

/** A sensible new window for a day: 18:00–19:00 for an empty day, else the hour after
 * the last window (shorter if midnight is closer). Null when the day is full to midnight. */
export function nextWindow(windows: Clock[]): Clock | null {
  if (windows.length === 0) return { start: "18:00", end: "19:00" };
  const last = Math.max(...windows.map((window) => toMinutes(window.end)));
  if (last >= 1440) return null;
  return { start: fromMinutes(last), end: fromMinutes(Math.min(last + 60, 1440)) };
}

/** Hours for a summary: "45 min", "12 h", "12.5 h" (to the nearest half hour). */
export function hoursText(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  return `${Math.round(minutes / 30) / 2} h`;
}

/** Today's date ("YYYY-MM-DD") in an IANA timezone. */
export function localToday(timeZone: string, now: Date = new Date()): string {
  // en-CA formats dates as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(now);
}

/** A "YYYY-MM-DD" date plus some days. */
export function addDays(date: string, days: number): string {
  const [y = 0, m = 1, d = 1] = date.split("-").map(Number);
  const moved = new Date(Date.UTC(y, m - 1, d + days));
  return moved.toISOString().slice(0, 10);
}

/** "Fri 27 Nov" for a "YYYY-MM-DD" date. */
export function shortDate(date: string): string {
  const [y = 0, m = 1, d = 1] = date.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** The browser's IANA timezones, with the current one included even if the list lacks it. */
export function timezoneOptions(current: string): string[] {
  let zones: string[];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch {
    zones = [];
  }
  return zones.includes(current) ? zones : [current, ...zones];
}

/** This device's timezone, if the browser says. */
export function deviceTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}
