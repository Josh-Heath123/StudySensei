/**
 * The session screen's state around the engine: is a session open, being
 * reflected on, or done? It restores the open session once per page load, keeps
 * a finished session (waiting for its reflection) across reloads, and reports
 * sync problems. Like the engine, it owns no timers and is plain TypeScript.
 */
import type { SessionEngine, Snapshot } from "@/session-engine/engine";
import { pendingStart, type FlushResult } from "@/session-engine/outbox";
import { readJson, writeJson, type KeyValueStore } from "@/session-engine/store";
import type { components } from "@/lib/api/schema";

export type ActiveSession = components["schemas"]["SessionDetailOut"];

export type SessionMeta = { moduleId: string; topicId: string | null };

/** An ended session, kept until its reflection is saved. */
export type Finished = SessionMeta & {
  startId: string;
  sessionId: string | null;
  activeMs: number;
  breakMs: number;
  eventCount: number;
};

export type ControllerState =
  | { status: "loading" }
  | { status: "none" }
  | { status: "open"; meta: SessionMeta }
  | { status: "reflecting"; finished: Finished }
  | { status: "done"; finished: Finished };

/** synced: nothing waiting. offline / retry: events are queued here for later. */
export type SyncStatus = FlushResult["status"];

type Command = "pause" | "resume" | "breakStart" | "breakEnd" | "end";

const FINISHED_KEY = "studysensei.session.finished";

export type ControllerOptions = {
  engine: SessionEngine;
  store: KeyValueStore;
  /** GET /sessions/active. Throws when the server can't be reached. */
  fetchActive: () => Promise<ActiveSession | null>;
};

export type SessionController = ReturnType<typeof createSessionController>;

export function createSessionController({ engine, store, fetchActive }: ControllerOptions) {
  let state: ControllerState = { status: "loading" };
  let sync: SyncStatus = "synced";
  let problems: string[] = [];
  let version = 0;
  let restoring: Promise<void> | null = null;
  const listeners = new Set<() => void>();

  function notify() {
    version += 1;
    for (const listener of listeners) listener();
  }

  function storedFinished(): Finished | null {
    const value = readJson<Finished | null>(store, FINISHED_KEY, null);
    return value !== null && typeof value === "object" && typeof value.startId === "string"
      ? value
      : null;
  }

  function finish(meta: SessionMeta, snap: Snapshot) {
    const stored = storedFinished();
    const finished: Finished =
      stored?.startId === snap.startId
        ? { ...stored, sessionId: snap.sessionId ?? stored.sessionId }
        : {
            ...meta,
            startId: snap.startId,
            sessionId: snap.sessionId,
            activeMs: snap.totals.activeMs,
            breakMs: snap.totals.breakMs,
            eventCount: snap.eventCount,
          };
    writeJson(store, FINISHED_KEY, finished);
    state = { status: "reflecting", finished };
  }

  /** Match the state to the engine after a restore or a command. */
  function settle(meta: SessionMeta | null) {
    const snap = engine.snapshot();
    if (snap !== null && meta !== null && snap.state === "ended") finish(meta, snap);
    else if (snap !== null && meta !== null) state = { status: "open", meta };
    else {
      const finished = storedFinished();
      state = finished ? { status: "reflecting", finished } : { status: "none" };
    }
  }

  async function load(): Promise<void> {
    let server: ActiveSession | null = null;
    let reached = true;
    try {
      server = await fetchActive();
    } catch {
      reached = false; // offline or a server error: fall back to what's queued here
    }
    engine.restore(server);
    let meta: SessionMeta | null = null;
    if (server !== null) meta = { moduleId: server.module_id, topicId: server.topic_id };
    else {
      const queued = pendingStart(store);
      if (queued) meta = { moduleId: queued.module_id, topicId: queued.topic_id ?? null };
    }
    settle(meta);
    sync = reached ? "synced" : "offline";
    notify();
    await after(engine.flush(), meta ?? metaOf(state));
  }

  /** Record a flush's outcome; anything the server refused means our copy is wrong. */
  async function after(flushing: Promise<FlushResult>, meta: SessionMeta | null) {
    const result = await flushing;
    sync = result.status;
    if (result.rejected.length > 0) {
      problems = [...problems, ...result.rejected.map((r) => r.message)];
      restoring = load();
      await restoring;
      return;
    }
    if (state.status === "reflecting" || state.status === "open") settle(meta);
    notify();
  }

  function currentMeta(): SessionMeta | null {
    return state.status === "open" ? state.meta : null;
  }

  async function run(command: Command): Promise<void> {
    const meta = currentMeta();
    const flushing = engine[command]();
    settle(meta);
    notify();
    await after(flushing, meta);
  }

  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    /** Changes whenever anything the screen shows (apart from the time) changes. */
    version: () => version,
    state: () => state,
    sync: () => sync,
    problems: () => problems,
    snapshot: () => engine.snapshot(),
    canRecord: engine.canRecord,

    /** Pick up the open (or finished) session. Runs once per page load; later calls share it. */
    restore(): Promise<void> {
      restoring ??= load();
      return restoring;
    },

    async start(meta: SessionMeta): Promise<void> {
      store.removeItem(FINISHED_KEY);
      problems = [];
      const flushing = engine.start(meta.moduleId, meta.topicId);
      state = { status: "open", meta };
      notify();
      await after(flushing, meta);
    },
    pause: () => run("pause"),
    resume: () => run("resume"),
    breakStart: () => run("breakStart"),
    breakEnd: () => run("breakEnd"),
    end: () => run("end"),

    async resolveAway(choice: "keep" | "pause" | "end"): Promise<void> {
      const meta = currentMeta();
      const flushing = engine.resolveAway(choice);
      settle(meta);
      notify();
      const result = await flushing;
      if (result !== null) await after(Promise.resolve(result), meta);
    },

    /** Call on every redraw: heartbeats, and the "you were away" check. */
    tick(): void {
      const before = engine.snapshot()?.away ?? null;
      const away = engine.tick();
      if ((before === null) !== (away === null)) notify();
    },

    /** Send anything queued (back online, or the tab is visible again). */
    async flush(): Promise<void> {
      await after(engine.flush(), currentMeta() ?? metaOf(state));
    },

    /** The finished session's server id, sending queued events first if it isn't known yet. */
    async sessionIdForReflection(): Promise<string | null> {
      if (state.status !== "reflecting") return null;
      if (state.finished.sessionId !== null) return state.finished.sessionId;
      await after(engine.flush(), metaOf(state));
      return state.status === "reflecting" ? state.finished.sessionId : null;
    },

    /** The reflection is saved: forget the finished session and show the summary. */
    reflected(): void {
      if (state.status !== "reflecting") return;
      store.removeItem(FINISHED_KEY);
      state = { status: "done", finished: state.finished };
      notify();
    },

    /** Leave without reflecting (the session's time is already saved). */
    skipReflection(): void {
      if (state.status !== "reflecting") return;
      store.removeItem(FINISHED_KEY);
      state = { status: "none" };
      notify();
    },

    dismissProblems(): void {
      problems = [];
      notify();
    },
  };
}

function metaOf(state: ControllerState): SessionMeta | null {
  if (state.status === "open") return state.meta;
  if (state.status === "reflecting" || state.status === "done") {
    return { moduleId: state.finished.moduleId, topicId: state.finished.topicId };
  }
  return null;
}
