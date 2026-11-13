import type { Snapshot } from "@/session-engine/engine";
import { DEFAULT_PLAN } from "@/session-engine/timer";

import { formatClock, timerView } from "./display";

const SEC = 1000;
const MIN = 60 * SEC;

function snap(overrides: Partial<Snapshot>): Snapshot {
  return {
    startId: "s1",
    sessionId: "server-1",
    eventCount: 1,
    state: "active",
    startedAt: 0,
    totals: { activeMs: 0, breakMs: 0 },
    cycle: { phase: "focus", focusMs: 0, breakDue: false, breakDueInMs: 50 * MIN },
    away: null,
    ...overrides,
  };
}

const focus = (focusMs: number) => ({
  phase: "focus" as const,
  focusMs,
  breakDue: focusMs >= 50 * MIN,
  breakDueInMs: Math.max(0, 50 * MIN - focusMs),
});

const onBreak = (breakElapsedMs: number) => ({
  phase: "break" as const,
  breakElapsedMs,
  breakRemainingMs: Math.max(0, 10 * MIN - breakElapsedMs),
  breakOverByMs: Math.max(0, breakElapsedMs - 10 * MIN),
});

describe("formatClock", () => {
  it("shows minutes and seconds, and hours once there are any", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(9 * SEC)).toBe("00:09");
    expect(formatClock(50 * MIN)).toBe("50:00");
    expect(formatClock(59 * MIN + 59 * SEC)).toBe("59:59");
    expect(formatClock(60 * MIN)).toBe("1:00:00");
    expect(formatClock(2 * 60 * MIN + 5 * MIN + 7 * SEC)).toBe("2:05:07");
  });

  it("drops partial seconds, and never shows a negative time", () => {
    expect(formatClock(1999)).toBe("00:01");
    expect(formatClock(-5 * SEC)).toBe("00:00");
  });
});

describe("timerView", () => {
  it("counts the focus block down, showing a full minute for the first second", () => {
    expect(timerView(snap({ cycle: focus(0) }), DEFAULT_PLAN)).toMatchObject({
      eyebrow: "Focus",
      numerals: "50:00",
      progress: 0,
      title: "50:00 focus · StudySensei",
    });
    expect(timerView(snap({ cycle: focus(400) }), DEFAULT_PLAN).numerals).toBe("50:00");
    expect(timerView(snap({ cycle: focus(10 * MIN) }), DEFAULT_PLAN)).toMatchObject({
      numerals: "40:00",
      progress: 0.2,
    });
  });

  it("fills the focus segment as the block passes", () => {
    const view = timerView(snap({ cycle: focus(25 * MIN) }), DEFAULT_PLAN);
    expect(view.segments).toEqual([
      { kind: "focus", label: "Focus 50 min", minutes: 50, filled: 0.5 },
      { kind: "break", label: "Break 10 min", minutes: 10, filled: 0 },
    ]);
  });

  it("counts up past the block once a break is due", () => {
    const view = timerView(snap({ cycle: focus(52 * MIN + 30 * SEC) }), DEFAULT_PLAN);
    expect(view).toMatchObject({
      eyebrow: "Focus · break due",
      numerals: "+02:30",
      progress: 1,
      title: "Break due · StudySensei",
    });
    expect(view.segments[0]?.filled).toBe(1);
  });

  it("freezes while paused and says so", () => {
    const view = timerView(snap({ state: "paused", cycle: focus(10 * MIN) }), DEFAULT_PLAN);
    expect(view).toMatchObject({
      eyebrow: "Paused",
      numerals: "40:00",
      title: "Paused · 40:00 · StudySensei",
    });
  });

  it("counts a break down, with the focus segment full", () => {
    const view = timerView(snap({ state: "on_break", cycle: onBreak(4 * MIN) }), DEFAULT_PLAN);
    expect(view).toMatchObject({
      eyebrow: "Break",
      numerals: "06:00",
      progress: 0.4,
      title: "06:00 break · StudySensei",
    });
    expect(view.segments.map((s) => s.filled)).toEqual([1, 0.4]);
  });

  it("counts up once a break runs over", () => {
    const view = timerView(
      snap({ state: "on_break", cycle: onBreak(12 * MIN + 5 * SEC) }),
      DEFAULT_PLAN,
    );
    expect(view).toMatchObject({
      eyebrow: "Break · over time",
      numerals: "+02:05",
      progress: 1,
      title: "Break over · StudySensei",
    });
  });

  it("shows the active total once the session has ended", () => {
    const view = timerView(
      snap({
        state: "ended",
        cycle: { phase: "ended" },
        totals: { activeMs: 75 * MIN, breakMs: 10 * MIN },
      }),
      DEFAULT_PLAN,
    );
    expect(view).toMatchObject({
      eyebrow: "Ended",
      numerals: "1:15:00",
      progress: 1,
      title: "Session ended · StudySensei",
    });
  });

  it("follows a different plan", () => {
    const view = timerView(snap({ cycle: { ...focus(0), breakDueInMs: 25 * MIN } }), {
      focusMin: 25,
      breakMin: 5,
    });
    expect(view.numerals).toBe("25:00");
    expect(view.segments.map((s) => s.label)).toEqual(["Focus 25 min", "Break 5 min"]);
  });
});
