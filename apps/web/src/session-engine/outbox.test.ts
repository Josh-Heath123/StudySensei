import { fakeSessionServer } from "@/test/fakeSessionServer";
import { json, mockApi } from "@/test/mockApi";

import {
  flushOutbox,
  pendingEvents,
  pendingStart,
  queueEvents,
  queueStart,
  rememberSessionId,
  serverSessionId,
  takeRejected,
} from "./outbox";
import { memoryStore } from "./store";

const iso = (minutes: number) => new Date(Date.UTC(2026, 10, 13, 8, minutes)).toISOString();

function startBody(id = "start-1") {
  return { module_id: "module-1", topic_id: null, start: { id, occurred_at: iso(0) } };
}

describe("outbox", () => {
  it("sends the start, learns the server id, then sends the events", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());
    queueEvents(store, "start-1", [{ id: "p1", type: "pause", occurred_at: iso(10) }]);

    expect(await flushOutbox(store)).toEqual({ status: "synced", rejected: [] });

    expect(serverSessionId(store, "start-1")).toBe("server-1");
    expect(server.only().events.map((e) => e.id)).toEqual(["start-1", "p1"]);
    expect(pendingStart(store)).toBeUndefined();
    expect(pendingEvents(store, "start-1")).toEqual([]);
  });

  it("keeps everything queued while offline and sends it once back online", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    server.setMode("offline");
    queueStart(store, startBody());
    queueEvents(store, "start-1", [{ id: "p1", type: "pause", occurred_at: iso(10) }]);

    expect((await flushOutbox(store)).status).toBe("offline");
    expect(pendingStart(store)?.start.id).toBe("start-1");
    expect(pendingEvents(store, "start-1")).toHaveLength(1);

    server.setMode("online");
    expect((await flushOutbox(store)).status).toBe("synced");
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "pause"]);
  });

  it("treats a retried duplicate as success (the reply was lost, not the request)", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());
    await flushOutbox(store);
    queueEvents(store, "start-1", [{ id: "p1", type: "pause", occurred_at: iso(10) }]);

    server.setMode("lose-response");
    expect((await flushOutbox(store)).status).toBe("offline");
    expect(pendingEvents(store, "start-1")).toHaveLength(1); // the client can't know it arrived

    server.setMode("online");
    expect(await flushOutbox(store)).toEqual({ status: "synced", rejected: [] });
    expect(pendingEvents(store, "start-1")).toEqual([]);
    // Sent twice, stored once.
    expect(server.calls.filter((c) => c.path.endsWith("/events"))).toHaveLength(2);
    expect(server.only().events.map((e) => e.id)).toEqual(["start-1", "p1"]);
  });

  it("treats a retried start as success too", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());
    server.setMode("lose-response");
    await flushOutbox(store);

    server.setMode("online");
    await flushOutbox(store);

    expect(serverSessionId(store, "start-1")).toBe("server-1");
    expect(server.sessions.size).toBe(1);
  });

  it("sends events for a session it learned about on restore", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());
    await flushOutbox(store);
    const other = memoryStore(); // e.g. a reload after storage was cleared
    rememberSessionId(other, "start-1", "server-1");
    queueEvents(other, "start-1", [{ id: "p1", type: "pause", occurred_at: iso(10) }]);

    await flushOutbox(other);

    expect(server.only().events).toHaveLength(2);
  });

  it("splits long queues into batches of 100", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());
    const events = Array.from({ length: 150 }, (_, i) => ({
      id: `e${i}`,
      type: i % 2 === 0 ? ("pause" as const) : ("resume" as const),
      occurred_at: iso(1 + i / 10),
    }));
    queueEvents(store, "start-1", events);

    await flushOutbox(store);

    const sizes = server.calls
      .filter((c) => c.path.endsWith("/events"))
      .map((c) => (c.body as { events: unknown[] }).events.length);
    expect(sizes).toEqual([100, 50]);
  });

  it("sets aside a batch the server rejects, instead of retrying it forever", async () => {
    const store = memoryStore();
    rememberSessionId(store, "start-1", "server-1");
    queueEvents(store, "start-1", [{ id: "r1", type: "resume", occurred_at: iso(10) }]);
    mockApi({
      "POST /sessions/:id/events": () => json({ detail: "Can't resume while active" }, 422),
    });

    const result = await flushOutbox(store);

    expect(result.status).toBe("synced");
    expect(result.rejected).toEqual([
      { startId: "start-1", status: 422, message: "Can't resume while active", eventIds: ["r1"] },
    ]);
    expect(pendingEvents(store, "start-1")).toEqual([]);
    expect(takeRejected(store)).toHaveLength(1);
    expect(takeRejected(store)).toEqual([]);
  });

  it("rejects a start (and its events) when another session is already open", async () => {
    const store = memoryStore();
    queueStart(store, startBody());
    queueEvents(store, "start-1", [{ id: "p1", type: "pause", occurred_at: iso(10) }]);
    mockApi({
      "POST /sessions": () => json({ detail: "Another session is still open; end it first" }, 409),
    });

    const { rejected } = await flushOutbox(store);

    expect(rejected).toEqual([
      {
        startId: "start-1",
        status: 409,
        message: "Another session is still open; end it first",
        eventIds: ["start-1", "p1"],
      },
    ]);
    expect(pendingStart(store)).toBeUndefined();
    expect(pendingEvents(store, "start-1")).toEqual([]);
  });

  it("keeps the queue and retries later on a server error", async () => {
    const store = memoryStore();
    queueStart(store, startBody());
    mockApi({ "POST /sessions": () => json({ detail: "Bad gateway" }, 502) });

    expect((await flushOutbox(store)).status).toBe("retry");
    expect(pendingStart(store)).toBeDefined();
  });

  it("runs one flush at a time", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());

    await Promise.all([flushOutbox(store), flushOutbox(store), flushOutbox(store)]);

    expect(server.calls.filter((c) => c.path === "/sessions")).toHaveLength(1);
  });

  it("also sends events queued while a flush was in flight", async () => {
    const server = fakeSessionServer();
    const store = memoryStore();
    queueStart(store, startBody());

    const flushing = flushOutbox(store);
    queueEvents(store, "start-1", [{ id: "p1", type: "pause", occurred_at: iso(10) }]);
    await flushing;

    expect(server.only().events.map((e) => e.id)).toEqual(["start-1", "p1"]);
  });

  it("survives a corrupt queue in storage", async () => {
    fakeSessionServer();
    const store = memoryStore();
    store.setItem("studysensei.session.outbox", "[[[");

    expect(await flushOutbox(store)).toEqual({ status: "synced", rejected: [] });
  });
});
