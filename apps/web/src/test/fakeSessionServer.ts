import type { components } from "@/lib/api/schema";

import { json, mockApi } from "./mockApi";

type StartBody = components["schemas"]["SessionStart"];
type EventBody = components["schemas"]["EventIn"];
type StoredEvent = { id: string; type: string; occurred_at: string };
type StoredSession = { id: string; events: StoredEvent[] };

/**
 * How the network behaves for the next requests:
 * - "online": normal replies
 * - "offline": fetch rejects before reaching the server
 * - "lose-response": the server stores the request, then the reply is lost
 */
export type NetworkMode = "online" | "offline" | "lose-response";

/**
 * A stand-in for the sessions API with the same idempotency rules as the server
 * (task 5): a resent start returns the same session (200), a resent event with
 * the same details is skipped, and the same id with other details is a 409.
 */
export function fakeSessionServer() {
  const sessions = new Map<string, StoredSession>();
  let mode: NetworkMode = "online";
  let nextId = 1;

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
    "POST /sessions": ({ body }) => {
      network();
      const { start } = body as StartBody;
      const existing = findByStart(start.id);
      if (existing) return reply(existing, 200);
      const session = {
        id: `server-${nextId++}`,
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
  });

  return {
    calls,
    sessions,
    setMode: (next: NetworkMode) => {
      mode = next;
    },
    /** The one session the server holds (fails the test if there isn't exactly one). */
    only(): StoredSession {
      expect(sessions.size).toBe(1);
      return [...sessions.values()][0]!;
    },
  };
}
