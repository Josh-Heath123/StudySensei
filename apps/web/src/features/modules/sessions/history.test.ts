import { activeSecondsAt, startOfWeek, timelineRows } from "./history";

describe("startOfWeek", () => {
  it("is Monday 00:00 local time", () => {
    // Friday 13 November 2026, 10:30
    expect(startOfWeek(new Date(2026, 10, 13, 10, 30))).toEqual(new Date(2026, 10, 9, 0, 0));
  });

  it("treats Sunday as the end of the week, and Monday as its own start", () => {
    expect(startOfWeek(new Date(2026, 10, 15, 23, 59))).toEqual(new Date(2026, 10, 9));
    expect(startOfWeek(new Date(2026, 10, 16, 0, 0))).toEqual(new Date(2026, 10, 16));
  });
});

describe("activeSecondsAt", () => {
  const base = { active_seconds: 600, last_event_at: "2026-11-13T08:10:00Z" };

  it("adds the running tail while the session is active", () => {
    const now = Date.parse("2026-11-13T08:15:00Z");
    expect(activeSecondsAt({ ...base, state: "active" }, now)).toBe(900);
  });

  it("uses the stored total otherwise", () => {
    const now = Date.parse("2026-11-13T08:15:00Z");
    expect(activeSecondsAt({ ...base, state: "paused" }, now)).toBe(600);
    expect(activeSecondsAt({ ...base, state: "on_break" }, now)).toBe(600);
    expect(activeSecondsAt({ ...base, state: "ended" }, now)).toBe(600);
  });

  it("never goes backwards if the clock is behind", () => {
    const now = Date.parse("2026-11-13T08:00:00Z");
    expect(activeSecondsAt({ ...base, state: "active" }, now)).toBe(600);
  });
});

describe("timelineRows", () => {
  it("names each event in order", () => {
    const at = (min: number) => new Date(Date.UTC(2026, 10, 13, 8, min)).toISOString();
    const rows = timelineRows([
      { id: "1", type: "start", occurred_at: at(0) },
      { id: "2", type: "pause", occurred_at: at(10) },
      { id: "3", type: "resume", occurred_at: at(12) },
      { id: "4", type: "break_start", occurred_at: at(50) },
      { id: "5", type: "break_end", occurred_at: at(60) },
      { id: "6", type: "end", occurred_at: at(70) },
    ]);
    expect(rows.map((r) => r.label)).toEqual([
      "Started",
      "Paused",
      "Resumed",
      "Break started",
      "Break ended",
      "Ended",
    ]);
    expect(rows[1]).toEqual({ id: "2", label: "Paused", at: at(10) });
  });
});
