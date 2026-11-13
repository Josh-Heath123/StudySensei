import { daysUntil, formatDue, fromIso, isPast, relativeDay, toIso } from "./dates";

// Built from local parts, so these tests pass in any timezone.
const local = (y: number, m: number, d: number, h = 0, min = 0) =>
  new Date(y, m - 1, d, h, min).toISOString();
const NOW = new Date(2026, 10, 16, 14, 30); // Mon 16 Nov 2026, 14:30 local

test("local date and time round-trip through ISO", () => {
  const iso = toIso("2026-11-28", "09:00");
  expect(iso).toBe(local(2026, 11, 28, 9, 0));
  expect(fromIso(iso)).toEqual({ date: "2026-11-28", time: "09:00" });
});

test("a missing time means midnight", () => {
  expect(toIso("2026-11-28", "")).toBe(local(2026, 11, 28));
});

test("formats a due date for display", () => {
  expect(formatDue(local(2026, 11, 28, 9, 0))).toBe("Sat 28 Nov, 09:00");
});

test("counts calendar days, not 24-hour periods", () => {
  // 23:59 tomorrow and 00:01 tomorrow are both "tomorrow".
  expect(daysUntil(local(2026, 11, 17, 0, 1), NOW)).toBe(1);
  expect(daysUntil(local(2026, 11, 17, 23, 59), NOW)).toBe(1);
  expect(daysUntil(local(2026, 11, 16, 23, 59), NOW)).toBe(0);
});

test.each([
  [local(2026, 11, 16, 18), "today"],
  [local(2026, 11, 17, 9), "tomorrow"],
  [local(2026, 11, 28, 9), "in 12 days"],
  [local(2026, 11, 15, 9), "yesterday"],
  [local(2026, 11, 13, 9), "3 days ago"],
])("relativeDay(%s) is %s", (iso, expected) => {
  expect(relativeDay(iso, NOW)).toBe(expected);
});

test("isPast compares the exact moment", () => {
  expect(isPast(local(2026, 11, 16, 14, 29), NOW)).toBe(true);
  expect(isPast(local(2026, 11, 16, 14, 31), NOW)).toBe(false);
});
