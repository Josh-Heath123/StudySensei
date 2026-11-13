import fixture from "../../../../fixtures/session-timelines.json";
import {
  canApply,
  cycleAt,
  DEFAULT_PLAN,
  detectAway,
  replay,
  stopClockEvents,
  TimelineError,
  totalsAt,
  type EventType,
  type TimerEvent,
} from "./timer";

const MIN = 60_000;
const T0 = Date.parse("2026-11-13T08:00:00.000Z");

/** Events from [type, minutes after T0], with seq in the order given. */
function log(...steps: [EventType, number][]): TimerEvent[] {
  return steps.map(([type, minutes], seq) => ({
    id: `e${seq}`,
    type,
    occurredAt: T0 + minutes * MIN,
    seq,
  }));
}

const at = (minutes: number) => T0 + minutes * MIN;

describe("shared fixture (same cases as the server's pytest)", () => {
  const base = Date.parse(fixture.t0);
  const offset = (seconds: number | null) => (seconds === null ? null : base + seconds * 1000);

  it.each(fixture.cases.map((c) => [c.name, c] as const))("%s", (_name, testCase) => {
    const events: TimerEvent[] = testCase.events.map((e, i) => ({
      id: `e${i}`,
      type: e.type as EventType,
      occurredAt: base + e.at * 1000,
      seq: e.seq,
    }));
    const expected = testCase.expect;

    if ("invalid" in expected) {
      expect(() => replay(events)).toThrow(TimelineError);
      return;
    }
    const timeline = replay(events);
    expect(timeline.state).toBe(expected.state);
    expect(timeline.activeMs / 1000).toBeCloseTo(expected.active_seconds, 6);
    expect(timeline.breakMs / 1000).toBeCloseTo(expected.break_seconds, 6);
    expect(timeline.lastEventAt).toBe(offset(expected.last_event_at));
    expect(timeline.endedAt).toBe(offset(expected.ended_at));
  });
});

describe("replay and live totals", () => {
  it("adds the live tail while active, on the injected clock", () => {
    const timeline = replay(log(["start", 0], ["pause", 10], ["resume", 15]));

    expect(totalsAt(timeline, at(15))).toEqual({ activeMs: 10 * MIN, breakMs: 0 });
    expect(totalsAt(timeline, at(40))).toEqual({ activeMs: 35 * MIN, breakMs: 0 });
  });

  it("adds nothing while paused, however long the pause", () => {
    const timeline = replay(log(["start", 0], ["pause", 10]));

    expect(totalsAt(timeline, at(500))).toEqual({ activeMs: 10 * MIN, breakMs: 0 });
  });

  it("counts a running break as break time", () => {
    const timeline = replay(log(["start", 0], ["break_start", 50]));

    expect(totalsAt(timeline, at(57))).toEqual({ activeMs: 50 * MIN, breakMs: 7 * MIN });
  });

  it("adds nothing after the end", () => {
    const timeline = replay(log(["start", 0], ["end", 30]));

    expect(totalsAt(timeline, at(90))).toEqual({ activeMs: 30 * MIN, breakMs: 0 });
  });

  it("never goes backwards if the clock does", () => {
    const timeline = replay(log(["start", 0]));

    expect(totalsAt(timeline, at(-5))).toEqual({ activeMs: 0, breakMs: 0 });
  });

  it("tracks focus since the last break", () => {
    const timeline = replay(
      log(["start", 0], ["pause", 10], ["resume", 12], ["break_start", 40], ["break_end", 50]),
    );

    expect(timeline.activeMs).toBe(38 * MIN);
    expect(timeline.focusSinceBreakMs).toBe(0);
    expect(timeline.breakStartedAt).toBeNull();
  });
});

describe("canApply", () => {
  it("only allows start without a session", () => {
    expect(canApply(null, "start")).toBe(true);
    expect(canApply(null, "pause")).toBe(false);
  });

  it.each([
    ["active", "pause", true],
    ["active", "break_start", true],
    ["active", "end", true],
    ["active", "resume", false],
    ["paused", "resume", true],
    ["paused", "break_start", false],
    ["on_break", "break_end", true],
    ["on_break", "end", true],
    ["on_break", "pause", false],
    ["ended", "resume", false],
    ["active", "start", false],
  ] as const)("%s + %s → %s", (state, type, allowed) => {
    expect(canApply(state, type)).toBe(allowed);
  });
});

describe("focus and break cycles", () => {
  it("shows a break as due after 50 focused minutes, without forcing one", () => {
    const timeline = replay(log(["start", 0]));

    expect(cycleAt(timeline, DEFAULT_PLAN, at(49))).toEqual({
      phase: "focus",
      focusMs: 49 * MIN,
      breakDue: false,
      breakDueInMs: 1 * MIN,
    });
    const due = cycleAt(timeline, DEFAULT_PLAN, at(65));
    expect(due).toEqual({ phase: "focus", focusMs: 65 * MIN, breakDue: true, breakDueInMs: 0 });
    // Still just active: nothing about the timeline changed.
    expect(timeline.state).toBe("active");
  });

  it("doesn't count paused time toward the next break", () => {
    const timeline = replay(log(["start", 0], ["pause", 30], ["resume", 60]));

    expect(cycleAt(timeline, DEFAULT_PLAN, at(70))).toMatchObject({
      focusMs: 40 * MIN,
      breakDue: false,
    });
  });

  it("times the break and how far it has run over", () => {
    const timeline = replay(log(["start", 0], ["break_start", 50]));

    expect(cycleAt(timeline, DEFAULT_PLAN, at(54))).toEqual({
      phase: "break",
      breakElapsedMs: 4 * MIN,
      breakRemainingMs: 6 * MIN,
      breakOverByMs: 0,
    });
    expect(cycleAt(timeline, DEFAULT_PLAN, at(63))).toMatchObject({
      breakRemainingMs: 0,
      breakOverByMs: 3 * MIN,
    });
  });

  it("starts a fresh focus count after a break", () => {
    const timeline = replay(log(["start", 0], ["break_start", 50], ["break_end", 60]));

    expect(cycleAt(timeline, DEFAULT_PLAN, at(80))).toMatchObject({
      focusMs: 20 * MIN,
      breakDueInMs: 30 * MIN,
    });
  });

  it("follows a custom plan", () => {
    const timeline = replay(log(["start", 0]));
    const plan = { focusMin: 25, breakMin: 5 };

    expect(cycleAt(timeline, plan, at(25))).toMatchObject({ breakDue: true });
  });

  it("has no cycle once ended", () => {
    expect(cycleAt(replay(log(["start", 0], ["end", 5])), DEFAULT_PLAN, at(9))).toEqual({
      phase: "ended",
    });
  });
});

describe("away detection", () => {
  const running = replay(log(["start", 0]));

  it("reports time away beyond two minutes while the clock runs", () => {
    expect(detectAway(running, at(10), at(10 + 192))).toEqual({
      since: at(10),
      awayMs: 192 * MIN,
    });
  });

  it("ignores short gaps, such as a quick reload", () => {
    expect(detectAway(running, at(10), at(11.5))).toBeNull();
  });

  it("ignores gaps while paused or ended, or without a last-active time", () => {
    expect(detectAway(replay(log(["start", 0], ["pause", 5])), at(5), at(300))).toBeNull();
    expect(detectAway(replay(log(["start", 0], ["end", 5])), at(5), at(300))).toBeNull();
    expect(detectAway(running, null, at(300))).toBeNull();
  });

  it("measures from the last event if that came after the last-active time", () => {
    const timeline = replay(log(["start", 0], ["break_start", 50], ["break_end", 60]));

    expect(detectAway(timeline, at(59.9), at(100))).toEqual({ since: at(60), awayMs: 40 * MIN });
  });
});

describe("stopping the clock when you left", () => {
  let n = 0;
  const newId = () => `new${n++}`;

  it("pauses or ends at the time you left, while active", () => {
    const timeline = replay(log(["start", 0]));

    expect(stopClockEvents(timeline, at(20), "pause", newId)).toEqual([
      { id: expect.any(String), type: "pause", occurredAt: at(20) },
    ]);
    expect(stopClockEvents(timeline, at(20), "end", newId)).toEqual([
      { id: expect.any(String), type: "end", occurredAt: at(20) },
    ]);
  });

  it("ends the break and pauses (or ends) while on a break", () => {
    const timeline = replay(log(["start", 0], ["break_start", 50]));

    expect(stopClockEvents(timeline, at(55), "pause", newId).map((e) => e.type)).toEqual([
      "break_end",
      "pause",
    ]);
    expect(stopClockEvents(timeline, at(55), "end", newId).map((e) => e.type)).toEqual(["end"]);
  });

  it("never lands before an event that's already recorded", () => {
    const timeline = replay(log(["start", 0], ["pause", 10], ["resume", 11]));

    const [pause] = stopClockEvents(timeline, at(10.5), "pause", newId);

    expect(pause?.occurredAt).toBe(at(11));
  });

  it("gives a valid timeline that excludes the time away", () => {
    const events = log(["start", 0]);
    const stop = stopClockEvents(replay(events), at(20), "pause", newId);
    const after = replay([...events, ...stop.map((e, i) => ({ ...e, seq: 10 + i }))]);

    expect(totalsAt(after, at(200))).toEqual({ activeMs: 20 * MIN, breakMs: 0 });
  });

  it("has nothing to stop while paused or ended", () => {
    expect(stopClockEvents(replay(log(["start", 0], ["pause", 5])), at(9), "end", newId)).toEqual(
      [],
    );
  });
});
