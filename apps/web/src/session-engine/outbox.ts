/**
 * The offline queue for session events, kept in localStorage.
 *
 * Every event carries its client UUID, so sending one twice is harmless: the
 * server answers 200 for a start or event it already has (decision 0003). That
 * makes "retry until it works" safe even when a request arrived but its reply
 * was lost.
 *
 * Sessions are keyed by their start event's id, so a session started offline can
 * queue events before the server has given it an id.
 */
import { api } from "@/lib/api/client";
import { ApiError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

import { readJson, writeJson, type KeyValueStore } from "./store";

export type StartBody = components["schemas"]["SessionStart"];
export type EventBody = components["schemas"]["EventIn"];

/** Something the server refused for good (409/422/404); it's dropped from the queue. */
export type Rejected = { startId: string; status: number; message: string; eventIds: string[] };

export type FlushResult = {
  /** synced: nothing sendable is left. offline: no connection. retry: a server error. */
  status: "synced" | "offline" | "retry";
  rejected: Rejected[];
};

type Outbox = {
  starts: StartBody[];
  events: { startId: string; event: EventBody }[];
  /** start event id -> server session id */
  sessionIds: Record<string, string>;
  rejected: Rejected[];
};

const KEY = "studysensei.session.outbox";
const BATCH_SIZE = 100;

function load(store: KeyValueStore): Outbox {
  const raw = readJson<Partial<Outbox> | null>(store, KEY, null);
  const isObject = typeof raw === "object" && raw !== null && !Array.isArray(raw);
  return {
    starts: isObject && Array.isArray(raw.starts) ? raw.starts : [],
    events: isObject && Array.isArray(raw.events) ? raw.events : [],
    sessionIds:
      isObject && typeof raw.sessionIds === "object" && raw.sessionIds !== null
        ? raw.sessionIds
        : {},
    rejected: isObject && Array.isArray(raw.rejected) ? raw.rejected : [],
  };
}

/** Read, change and save the queue in one step (no await in between). */
function update(store: KeyValueStore, change: (outbox: Outbox) => void): void {
  const outbox = load(store);
  change(outbox);
  writeJson(store, KEY, outbox);
}

export function queueStart(store: KeyValueStore, body: StartBody): void {
  update(store, (o) => {
    if (!o.starts.some((s) => s.start.id === body.start.id)) o.starts.push(body);
  });
}

export function queueEvents(store: KeyValueStore, startId: string, events: EventBody[]): void {
  update(store, (o) => {
    for (const event of events) {
      if (!o.events.some((q) => q.event.id === event.id)) o.events.push({ startId, event });
    }
  });
}

/** The newest start not yet accepted by the server, if any. */
export function pendingStart(store: KeyValueStore): StartBody | undefined {
  return load(store).starts.at(-1);
}

export function pendingEvents(store: KeyValueStore, startId: string): EventBody[] {
  return load(store)
    .events.filter((q) => q.startId === startId)
    .map((q) => q.event);
}

export function serverSessionId(store: KeyValueStore, startId: string): string | undefined {
  return load(store).sessionIds[startId];
}

/** Record a session's server id (learned from a start reply or from the server on reload). */
export function rememberSessionId(store: KeyValueStore, startId: string, sessionId: string): void {
  update(store, (o) => {
    o.sessionIds[startId] = sessionId;
  });
}

/** Drop a finished session's id once nothing for it is queued. */
export function forgetSession(store: KeyValueStore, startId: string): void {
  update(store, (o) => {
    const queued =
      o.starts.some((s) => s.start.id === startId) || o.events.some((q) => q.startId === startId);
    if (!queued) delete o.sessionIds[startId];
  });
}

/** Rejections not yet shown to the student; reading them clears them. */
export function takeRejected(store: KeyValueStore): Rejected[] {
  const { rejected } = load(store);
  if (rejected.length > 0) update(store, (o) => void (o.rejected = []));
  return rejected;
}

/** Try again later: no connection, or a server-side failure. */
type Later = "offline" | "retry";
type Sent =
  | { ok: true; data: { id: string } }
  | { ok: false; later: Later }
  | { ok: false; refused: ApiError };
type Call = Promise<{ data?: { id: string }; error?: unknown; response: Response }>;

async function send(call: Call): Promise<Sent> {
  try {
    return { ok: true, data: await unwrap(call) };
  } catch (error) {
    // fetch itself rejected: the request may or may not have arrived. Resending is safe.
    if (!(error instanceof ApiError)) return { ok: false, later: "offline" };
    const transient = error.status >= 500 || error.status === 408 || error.status === 429;
    return transient ? { ok: false, later: "retry" } : { ok: false, refused: error };
  }
}

function reject(store: KeyValueStore, item: Rejected, found: Rejected[]): void {
  const ids = new Set(item.eventIds);
  update(store, (o) => {
    o.starts = o.starts.filter((s) => !ids.has(s.start.id));
    o.events = o.events.filter((q) => !ids.has(q.event.id));
    o.rejected.push(item);
  });
  found.push(item);
}

/** Send the next piece of work: "sent" (or refused), "idle" if nothing is sendable, or Later. */
async function step(store: KeyValueStore, found: Rejected[]): Promise<"sent" | "idle" | Later> {
  const outbox = load(store);

  const start = outbox.starts[0];
  if (start !== undefined) {
    const startId = start.start.id;
    const sent = await send(api.POST("/sessions", { body: start }));
    if (sent.ok) {
      update(store, (o) => {
        o.starts = o.starts.filter((s) => s.start.id !== startId);
        o.sessionIds[startId] = sent.data.id;
      });
      return "sent";
    }
    if ("later" in sent) return sent.later;
    // Its events can never be sent either.
    const eventIds = [startId, ...pendingEvents(store, startId).map((e) => e.id)];
    const { status, message } = sent.refused;
    reject(store, { startId, status, message, eventIds }, found);
    return "sent";
  }

  const next = outbox.events.find((q) => outbox.sessionIds[q.startId] !== undefined);
  if (next === undefined) return "idle";
  const { startId } = next;
  const batch = outbox.events
    .filter((q) => q.startId === startId)
    .slice(0, BATCH_SIZE)
    .map((q) => q.event);
  const sent = await send(
    api.POST("/sessions/{session_id}/events", {
      params: { path: { session_id: outbox.sessionIds[startId]! } },
      body: { events: batch },
    }),
  );
  if ("later" in sent) return sent.later;
  const sentIds = new Set(batch.map((e) => e.id));
  if (sent.ok) {
    update(store, (o) => void (o.events = o.events.filter((q) => !sentIds.has(q.event.id))));
  } else {
    const { status, message } = sent.refused;
    reject(store, { startId, status, message, eventIds: [...sentIds] }, found);
  }
  return "sent";
}

const inFlight = new WeakMap<KeyValueStore, Promise<FlushResult>>();

/**
 * Send everything queued: starts first, then events in batches of up to 100.
 * Only one flush runs per store; overlapping calls share it. Events queued while
 * it runs are picked up before it finishes.
 */
export function flushOutbox(store: KeyValueStore): Promise<FlushResult> {
  const running = inFlight.get(store);
  if (running) return running;
  const flush = (async (): Promise<FlushResult> => {
    const rejected: Rejected[] = [];
    try {
      for (;;) {
        const progress = await step(store, rejected);
        if (progress === "idle") return { status: "synced", rejected };
        if (progress !== "sent") return { status: progress, rejected };
      }
    } finally {
      inFlight.delete(store);
    }
  })();
  inFlight.set(store, flush);
  return flush;
}
