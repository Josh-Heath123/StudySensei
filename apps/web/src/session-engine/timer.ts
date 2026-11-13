/**
 * The study timer, as pure functions of the session's events and an injected `now`.
 *
 * Elapsed time always comes from event timestamps; a display tick only redraws.
 * `replay` mirrors the server's `app/services/sessions/timeline.py`, and both run
 * the shared cases in `fixtures/session-timelines.json`, so they can't drift apart.
 *
 *     (none) --start--> active
 *     active --pause--> paused --resume--> active
 *     active --break_start--> on_break --break_end--> active
 *     active | paused | on_break --end--> ended
 */

export type EventType = "start" | "pause" | "resume" | "break_start" | "break_end" | "end";
export type TimerState = "active" | "paused" | "on_break" | "ended";

/** One timer event. Times are epoch milliseconds on the client's clock. */
export type TimerEvent = {
  id: string;
  type: EventType;
  occurredAt: number;
  /** Tie-break for equal timestamps: the order the events were made in. */
  seq: number;
};

/** An event about to be recorded (the engine gives it a seq). */
export type NewEvent = Omit<TimerEvent, "seq">;

export type Timeline = {
  state: TimerState;
  startedAt: number;
  endedAt: number | null;
  lastEventAt: number;
  /** Totals up to `lastEventAt`; `totalsAt` adds the live tail. */
  activeMs: number;
  breakMs: number;
  /** Active time since the last break ended (or the start), up to `lastEventAt`. */
  focusSinceBreakMs: number;
  /** When the current break started, while on a break. */
  breakStartedAt: number | null;
};

export class TimelineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimelineError";
  }
}

// (state before, event) -> state after. Anything missing is illegal. Same table as the server.
const TRANSITIONS: Record<TimerState, Partial<Record<EventType, TimerState>>> = {
  active: { pause: "paused", break_start: "on_break", end: "ended" },
  paused: { resume: "active", end: "ended" },
  on_break: { break_end: "active", end: "ended" },
  ended: {},
};

/** Whether `type` can be recorded now. `null` means there's no session yet. */
export function canApply(state: TimerState | null, type: EventType): boolean {
  if (state === null) return type === "start";
  return TRANSITIONS[state][type] !== undefined;
}

/** Sort by (occurredAt, seq) and walk the state machine. Throws `TimelineError`. */
export function replay(events: readonly TimerEvent[]): Timeline {
  const ordered = [...events].sort((a, b) => a.occurredAt - b.occurredAt || a.seq - b.seq);
  const [first, ...rest] = ordered;
  if (first === undefined) throw new TimelineError("A session needs a start event");
  if (first.type !== "start") {
    throw new TimelineError(`No event can come before the session's start (${first.type})`);
  }

  let state: TimerState = "active";
  let since = first.occurredAt;
  let activeMs = 0;
  let breakMs = 0;
  let focusSinceBreakMs = 0;
  let breakStartedAt: number | null = null;
  for (const event of rest) {
    if (state === "ended") {
      throw new TimelineError(`The session has ended; ${event.type} can't come after it`);
    }
    const after: TimerState | undefined = TRANSITIONS[state][event.type];
    if (after === undefined) throw new TimelineError(`Can't ${event.type} while ${state}`);
    const elapsed = event.occurredAt - since;
    if (state === "active") {
      activeMs += elapsed;
      focusSinceBreakMs += elapsed;
    } else if (state === "on_break") {
      breakMs += elapsed;
    }
    if (event.type === "break_start") breakStartedAt = event.occurredAt;
    if (event.type === "break_end") {
      breakStartedAt = null;
      focusSinceBreakMs = 0;
    }
    state = after;
    since = event.occurredAt;
  }

  return {
    state,
    startedAt: first.occurredAt,
    endedAt: state === "ended" ? since : null,
    lastEventAt: since,
    activeMs,
    breakMs,
    focusSinceBreakMs,
    breakStartedAt: state === "on_break" ? breakStartedAt : null,
  };
}

export type Totals = { activeMs: number; breakMs: number };

/** Time since the last event while the clock runs (never negative if the clock goes back). */
function liveTail(timeline: Timeline, now: number): number {
  return Math.max(0, now - timeline.lastEventAt);
}

/** Active and break time as of `now`. */
export function totalsAt(timeline: Timeline, now: number): Totals {
  const tail = liveTail(timeline, now);
  return {
    activeMs: timeline.activeMs + (timeline.state === "active" ? tail : 0),
    breakMs: timeline.breakMs + (timeline.state === "on_break" ? tail : 0),
  };
}

/** How long to focus before a break, and how long the break is. */
export type CyclePlan = { focusMin: number; breakMin: number };

export const DEFAULT_PLAN: CyclePlan = { focusMin: 50, breakMin: 10 };

export type Cycle =
  | { phase: "focus"; focusMs: number; breakDue: boolean; breakDueInMs: number }
  | { phase: "break"; breakElapsedMs: number; breakRemainingMs: number; breakOverByMs: number }
  | { phase: "ended" };

/**
 * Where the session is in its focus/break cycle. "Break due" is information for
 * the screen; nothing here (or anywhere) starts a break by itself.
 */
export function cycleAt(timeline: Timeline, plan: CyclePlan, now: number): Cycle {
  if (timeline.state === "ended") return { phase: "ended" };
  if (timeline.state === "on_break") {
    const target = plan.breakMin * 60_000;
    const breakElapsedMs = Math.max(0, now - (timeline.breakStartedAt ?? timeline.lastEventAt));
    return {
      phase: "break",
      breakElapsedMs,
      breakRemainingMs: Math.max(0, target - breakElapsedMs),
      breakOverByMs: Math.max(0, breakElapsedMs - target),
    };
  }
  const target = plan.focusMin * 60_000;
  const focusMs =
    timeline.focusSinceBreakMs + (timeline.state === "active" ? liveTail(timeline, now) : 0);
  return {
    phase: "focus",
    focusMs,
    breakDue: focusMs >= target,
    breakDueInMs: Math.max(0, target - focusMs),
  };
}

/** A gap longer than this while the clock runs means the student was probably away. */
export const AWAY_THRESHOLD_MS = 2 * 60_000;

export type Away = { since: number; awayMs: number };

/**
 * Whether the student seems to have been away: the clock was running and nothing
 * was seen of the page between `lastSeenAt` (a heartbeat or the previous tick)
 * and `now`. Measured from the later of `lastSeenAt` and the last event.
 */
export function detectAway(
  timeline: Timeline | null,
  lastSeenAt: number | null,
  now: number,
  thresholdMs: number = AWAY_THRESHOLD_MS,
): Away | null {
  if (timeline === null || lastSeenAt === null) return null;
  if (timeline.state !== "active" && timeline.state !== "on_break") return null;
  const since = Math.max(lastSeenAt, timeline.lastEventAt);
  const awayMs = now - since;
  return awayMs > thresholdMs ? { since, awayMs } : null;
}

/**
 * The events that stop the clock at `since` (when the student left): a pause or
 * an end. On a break, "pause" first ends the break, so the away time counts as
 * neither. Never earlier than the last recorded event, so the log stays valid.
 */
export function stopClockEvents(
  timeline: Timeline,
  since: number,
  choice: "pause" | "end",
  newId: () => string,
): NewEvent[] {
  const at = Math.max(since, timeline.lastEventAt);
  const make = (type: EventType): NewEvent => ({ id: newId(), type, occurredAt: at });
  if (timeline.state === "active") return [make(choice)];
  if (timeline.state === "on_break") {
    return choice === "end" ? [make("end")] : [make("break_end"), make("pause")];
  }
  return [];
}
