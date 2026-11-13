/**
 * The study-session engine the session screen drives.
 *
 * It owns no timers and never reads the system clock: `now` is injected, and the
 * screen calls `tick()` on its redraw interval and `snapshot()` to render. Every
 * number comes from event timestamps (see timer.ts), so a throttled tab, a
 * reload or a sleeping laptop can't make the clock drift.
 *
 * Commands record an event locally first (so the screen updates at once), queue
 * it in the outbox and try to send it; offline, it's sent later.
 */
import type { components } from "@/lib/api/schema";

import { formatDuration } from "./format";
import { clearActive, HEARTBEAT_MS, lastActive, recordActive } from "./heartbeat";
import {
  flushOutbox,
  forgetSession,
  pendingEvents,
  pendingStart,
  queueEvents,
  queueStart,
  rememberSessionId,
  serverSessionId,
  type EventBody,
  type FlushResult,
} from "./outbox";
import type { KeyValueStore } from "./store";
import {
  canApply,
  cycleAt,
  DEFAULT_PLAN,
  detectAway,
  replay,
  stopClockEvents,
  TimelineError,
  totalsAt,
  type Away,
  type Cycle,
  type CyclePlan,
  type EventType,
  type NewEvent,
  type Timeline,
  type TimerEvent,
  type TimerState,
  type Totals,
} from "./timer";

/** What the server returns for a session (only the parts the engine needs). */
export type ServerSession = Pick<components["schemas"]["SessionDetailOut"], "id" | "events">;

export type AwayPrompt = Away & { message: string };

export type Snapshot = {
  /** The start event's client id: the session's key until the server id is known. */
  startId: string;
  /** The server's id, once the start has been accepted. */
  sessionId: string | null;
  state: TimerState;
  startedAt: number;
  totals: Totals;
  cycle: Cycle;
  /** An unanswered "you were away" question, if any. */
  away: AwayPrompt | null;
};

export type EngineOptions = {
  now: () => number;
  newId: () => string;
  store: KeyValueStore;
  plan?: CyclePlan;
};

export type SessionEngine = ReturnType<typeof createSessionEngine>;

const iso = (ms: number) => new Date(ms).toISOString();

function awayPrompt(away: Away): AwayPrompt {
  return {
    ...away,
    message: `You were away for ${formatDuration(away.awayMs)}. Keep that time, or stop the clock when you left?`,
  };
}

export function createSessionEngine({ now, newId, store, plan = DEFAULT_PLAN }: EngineOptions) {
  let startId: string | null = null;
  let events: TimerEvent[] = [];
  let timeline: Timeline | null = null;
  let away: AwayPrompt | null = null;
  // When the page was last seen running (the previous tick), and the last heartbeat.
  let lastTick: number | null = null;
  let lastBeat = -Infinity;

  const isOpen = () => timeline !== null && timeline.state !== "ended";

  function beat(at: number) {
    if (startId === null) return;
    recordActive(store, startId, at);
    lastBeat = at;
  }

  /** Validate and keep new events (seq continues after the existing ones). */
  function append(added: NewEvent[]) {
    const next = [...events, ...added.map((e, i) => ({ ...e, seq: events.length + i }))];
    timeline = replay(next);
    events = next;
  }

  async function flush(): Promise<FlushResult> {
    const result = await flushOutbox(store);
    if (startId !== null && timeline?.state === "ended" && result.status === "synced") {
      forgetSession(store, startId);
    }
    return result;
  }

  function record(added: NewEvent[]): Promise<FlushResult> {
    if (startId === null) throw new TimelineError("No session is open");
    append(added);
    const at = now();
    queueEvents(
      store,
      startId,
      added.map((e) => ({ id: e.id, type: e.type, occurred_at: iso(e.occurredAt) }) as EventBody),
    );
    if (timeline?.state === "ended") clearActive(store);
    else beat(at);
    lastTick = at;
    return flush();
  }

  /** Record `type` now (never before the last event, in case the clock went back). */
  async function command(type: Exclude<EventType, "start">): Promise<FlushResult> {
    if (timeline === null || !canApply(timeline.state, type)) {
      throw new TimelineError(`Can't ${type} while ${timeline?.state ?? "no session is open"}`);
    }
    const occurredAt = Math.max(now(), timeline.lastEventAt);
    return record([{ id: newId(), type, occurredAt }]);
  }

  return {
    /** Start a new session now. */
    async start(moduleId: string, topicId: string | null = null): Promise<FlushResult> {
      if (isOpen()) throw new TimelineError("A session is already open");
      const at = now();
      const id = newId();
      startId = id;
      events = [];
      away = null;
      append([{ id, type: "start", occurredAt: at }]);
      queueStart(store, {
        module_id: moduleId,
        topic_id: topicId,
        start: { id, occurred_at: iso(at) },
      });
      beat(at);
      lastTick = at;
      return flush();
    },
    pause: () => command("pause"),
    resume: () => command("resume"),
    breakStart: () => command("break_start"),
    breakEnd: () => command("break_end"),
    end: () => command("end"),

    /** Whether the screen should offer this command now. */
    canRecord(type: EventType): boolean {
      return isOpen() ? canApply(timeline!.state, type) : type === "start";
    },

    /**
     * Pick up the open session after a page load: the server's copy (from
     * GET /sessions/active) merged with anything still queued here. Returns a
     * "you were away" prompt if the clock ran while the page was gone.
     */
    restore(server: ServerSession | null): AwayPrompt | null {
      const at = now();
      let base: NewEvent[];
      if (server !== null) {
        const start = server.events.find((e) => e.type === "start");
        if (start === undefined) return null;
        startId = start.id;
        rememberSessionId(store, startId, server.id);
        base = server.events.map((e) => ({
          id: e.id,
          type: e.type,
          occurredAt: Date.parse(e.occurred_at),
        }));
      } else {
        const queued = pendingStart(store);
        if (queued === undefined) {
          startId = null;
          events = [];
          timeline = null;
          return null;
        }
        startId = queued.start.id;
        base = [{ id: startId, type: "start", occurredAt: Date.parse(queued.start.occurred_at) }];
      }

      const known = new Set(base.map((e) => e.id));
      const queued = pendingEvents(store, startId)
        .filter((e) => !known.has(e.id))
        .map((e) => ({ id: e.id, type: e.type, occurredAt: Date.parse(e.occurred_at) }));
      events = [];
      try {
        append([...base, ...queued]);
      } catch {
        // The queued events no longer fit the server's log; the server's copy wins.
        append(base);
      }

      lastTick = at;
      away = null;
      const gone = detectAway(timeline, lastActive(store, startId), at);
      if (gone !== null) away = awayPrompt(gone);
      else if (isOpen()) beat(at);
      return away;
    },

    /**
     * Call on every display tick. Records the heartbeat every 15 s, and returns
     * a "you were away" prompt when the gap since the last tick shows the page
     * was asleep. Until it's answered, the prompt keeps coming back.
     */
    tick(): AwayPrompt | null {
      const at = now();
      if (away !== null) return away;
      const gone = detectAway(timeline, lastTick, at);
      lastTick = at;
      if (gone !== null) {
        away = awayPrompt(gone);
        return away;
      }
      if (isOpen() && at - lastBeat >= HEARTBEAT_MS) beat(at);
      return null;
    },

    /** Answer the prompt: keep the time, or stop the clock (pause or end) when the student left. */
    async resolveAway(choice: "keep" | "pause" | "end"): Promise<FlushResult | null> {
      if (away === null || timeline === null) return null;
      const { since } = away;
      away = null;
      if (choice === "keep") {
        beat(now());
        lastTick = now();
        return null;
      }
      return record(stopClockEvents(timeline, since, choice, newId));
    },

    /** Send anything queued (e.g. when the browser comes back online). */
    flush,

    /** Everything the screen needs to draw, as of `now()`. */
    snapshot(): Snapshot | null {
      if (timeline === null || startId === null) return null;
      const at = now();
      return {
        startId,
        sessionId: serverSessionId(store, startId) ?? null,
        state: timeline.state,
        startedAt: timeline.startedAt,
        totals: totalsAt(timeline, at),
        cycle: cycleAt(timeline, plan, at),
        away,
      };
    },
  };
}
