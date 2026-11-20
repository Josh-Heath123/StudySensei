import type { components } from "@/lib/api/schema";

import { json, mockApi, type Handler } from "./mockApi";

type StartBody = components["schemas"]["SessionStart"];
type EventBody = components["schemas"]["EventIn"];
type StoredEvent = components["schemas"]["EventOut"];
type ReflectionBody = components["schemas"]["ReflectionIn"];
type StoredSession = {
  id: string;
  module_id: string;
  topic_id: string | null;
  plan_block_id: string | null;
  events: StoredEvent[];
  reflection?: ReflectionBody;
};

/**
 * How the network behaves for the next requests:
 * - "online": normal replies
 * - "offline": fetch rejects before reaching the server
 * - "lose-response": the server stores the request, then the reply is lost
 */
export type NetworkMode = "online" | "offline" | "lose-response";

const isOpen = (s: StoredSession) => s.events.at(-1)?.type !== "end";

/**
 * A stand-in for the sessions API with the same idempotency rules as the server
 * (task 5): a resent start returns the same session (200), a resent event with
 * the same details is skipped, and the same id with other details is a 409. Only
 * one session can be open at a time. `extra` adds routes (modules, topics, …).
 */
export function fakeSessionServer(extra: Record<string, Handler> = {}) {
  const sessions = new Map<string, StoredSession>();
  let mode: NetworkMode = "online";
  let nextId = 1;
  // Plan blocks the server refuses to start a session for (the plan changed).
  const staleBlocks = new Set<string>();

  const network = () => {
    if (mode === "offline") throw new TypeError("Failed to fetch");
  };
  const reply = (body: unknown, status: number) => {
    if (mode === "lose-response") throw new TypeError("Network connection was lost");
    return json(body, status);
  };
  const findByStart = (startId: string) =>
    [...sessions.values()].find((s) => s.events[0]?.id === startId);

  const { calls } = mockApi({
    ...extra,
    "GET /sessions/active": () => {
      network();
      return reply([...sessions.values()].find(isOpen) ?? null, 200);
    },
    "POST /sessions": ({ body }) => {
      network();
      const { start, module_id, topic_id, plan_block_id } = body as StartBody;
      const existing = findByStart(start.id);
      if (existing) return reply(existing, 200);
      if (plan_block_id && staleBlocks.has(plan_block_id)) {
        return json({ detail: "Only a planned block of the current plan can be started." }, 409);
      }
      if ([...sessions.values()].some(isOpen)) {
        return json({ detail: "Another session is still open; end it first" }, 409);
      }
      const session: StoredSession = {
        id: `server-${nextId++}`,
        module_id,
        topic_id: topic_id ?? null,
        plan_block_id: plan_block_id ?? null,
        events: [{ id: start.id, type: "start", occurred_at: start.occurred_at }],
      };
      sessions.set(session.id, session);
      return reply(session, 201);
    },
    "POST /sessions/:id/events": ({ params, body }) => {
      network();
      const session = sessions.get(params.id!);
      if (!session) return json({ detail: "Session not found" }, 404);
      for (const event of (body as { events: EventBody[] }).events) {
        const stored = session.events.find((e) => e.id === event.id);
        if (stored && (stored.type !== event.type || stored.occurred_at !== event.occurred_at)) {
          return json({ detail: `Event ${event.id} was already recorded differently` }, 409);
        }
        if (!stored) session.events.push({ ...event });
      }
      session.events.sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at));
      return reply(session, 200);
    },
    "PUT /sessions/:id/reflection": ({ params, body }) => {
      network();
      const session = sessions.get(params.id!);
      if (!session) return json({ detail: "Session not found" }, 404);
      if (isOpen(session)) {
        return json({ detail: "Reflect on a session once it has ended" }, 422);
      }
      session.reflection = body as ReflectionBody;
      return reply(session, 200);
    },
  });

  return {
    calls,
    sessions,
    setMode: (next: NetworkMode) => {
      mode = next;
    },
    /** From now on, refuse starts for this plan block (409). */
    refuseBlock: (blockId: string) => void staleBlocks.add(blockId),
    /** The one session the server holds (fails the test if there isn't exactly one). */
    only(): StoredSession {
      expect(sessions.size).toBe(1);
      return [...sessions.values()][0]!;
    },
  };
}
