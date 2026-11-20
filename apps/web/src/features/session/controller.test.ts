import { createSessionEngine } from "@/session-engine/engine";
import { memoryStore, type KeyValueStore } from "@/session-engine/store";
import { fakeSessionServer } from "@/test/fakeSessionServer";

import { fetchActiveSession } from "./api";
import { createSessionController } from "./controller";

const MIN = 60_000;
const T0 = Date.parse("2026-11-13T08:00:00.000Z");
const META = { moduleId: "m1", topicId: "t1", planBlockId: null };

/** A shared clock and store; each `page()` is a fresh page load. */
function world(prefix = "id") {
  let t = T0;
  let n = 0;
  const store = memoryStore();
  const page = (s: KeyValueStore = store) =>
    createSessionController({
      engine: createSessionEngine({ now: () => t, newId: () => `${prefix}-${++n}`, store: s }),
      store: s,
      fetchActive: fetchActiveSession,
    });
  return { store, page, wait: (ms: number) => void (t += ms) };
}

describe("session controller", () => {
  it("has nothing to restore when no session is open", async () => {
    fakeSessionServer();
    const controller = world().page();
    expect(controller.state()).toEqual({ status: "loading" });

    await controller.restore();

    expect(controller.state()).toEqual({ status: "none" });
  });

  it("restores the server's open session with its module and topic", async () => {
    const server = fakeSessionServer();
    const { page, wait } = world();
    const first = page();
    await first.restore();
    await first.start(META);
    wait(10 * MIN);
    await first.pause();

    const second = page();
    await second.restore();

    expect(second.state()).toEqual({ status: "open", meta: META });
    expect(second.snapshot()).toMatchObject({ state: "paused", sessionId: "server-1" });
    expect(server.calls.filter((c) => c.path === "/sessions/active")).toHaveLength(2);
  });

  it("restores from the local queue when the server can't be reached", async () => {
    const server = fakeSessionServer();
    server.setMode("offline");
    const { page } = world();
    const first = page();
    await first.restore();
    await first.start(META);
    expect(first.sync()).toBe("offline");

    const second = page();
    await second.restore();

    expect(second.state()).toEqual({ status: "open", meta: META });
    expect(second.sync()).toBe("offline");
    server.setMode("online");
    await second.flush();
    expect(second.sync()).toBe("synced");
    expect(server.only().events.map((e) => e.type)).toEqual(["start"]);
  });

  it("restores only once per page load", async () => {
    const server = fakeSessionServer();
    const controller = world().page();

    await Promise.all([controller.restore(), controller.restore()]);
    await controller.restore();

    expect(server.calls.filter((c) => c.path === "/sessions/active")).toHaveLength(1);
  });

  it("when the server refuses a start, says why and shows the session that's really open", async () => {
    const server = fakeSessionServer();
    const here = world().page();
    await here.restore();
    expect(here.state()).toEqual({ status: "none" });

    const elsewhere = world("other").page(); // another device, after this tab loaded
    await elsewhere.restore();
    await elsewhere.start({ moduleId: "m2", topicId: null, planBlockId: null });

    await here.start(META);

    expect(here.problems()).toEqual(["Another session is still open; end it first"]);
    expect(here.state()).toEqual({
      status: "open",
      meta: { moduleId: "m2", topicId: null, planBlockId: null },
    });
    expect(here.snapshot()?.sessionId).toBe("server-1");
    expect(server.sessions.size).toBe(1);
  });

  it("ends into the reflection, which survives a reload until it's saved", async () => {
    const server = fakeSessionServer();
    const { page, wait } = world();
    const first = page();
    await first.restore();
    await first.start(META);
    wait(30 * MIN);
    await first.end();

    const finished = {
      ...META,
      startId: "id-1",
      sessionId: "server-1",
      activeMs: 30 * MIN,
      breakMs: 0,
      eventCount: 2,
    };
    expect(first.state()).toEqual({ status: "reflecting", finished });

    const second = page();
    await second.restore();
    expect(second.state()).toEqual({ status: "reflecting", finished });
    expect(await second.sessionIdForReflection()).toBe("server-1");

    second.reflected();
    expect(second.state()).toEqual({ status: "done", finished });
    const third = page();
    await third.restore();
    expect(third.state()).toEqual({ status: "none" });
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "end"]);
  });

  it("finds the server id for a session that started and ended offline", async () => {
    const server = fakeSessionServer();
    server.setMode("offline");
    const { page, wait } = world();
    const controller = page();
    await controller.restore();
    await controller.start(META);
    wait(5 * MIN);
    await controller.end();
    expect(await controller.sessionIdForReflection()).toBeNull();

    server.setMode("online");
    expect(await controller.sessionIdForReflection()).toBe("server-1");
    expect(controller.state()).toMatchObject({ finished: { sessionId: "server-1" } });
  });

  it("can skip the reflection", async () => {
    fakeSessionServer();
    const { page } = world();
    const controller = page();
    await controller.restore();
    await controller.start(META);
    await controller.end();

    controller.skipReflection();

    expect(controller.state()).toEqual({ status: "none" });
    const reloaded = page();
    await reloaded.restore();
    expect(reloaded.state()).toEqual({ status: "none" });
  });

  it("notifies subscribers when the away question appears", async () => {
    fakeSessionServer();
    const { page, wait } = world();
    const controller = page();
    await controller.restore();
    await controller.start(META);
    const seen: number[] = [];
    controller.subscribe(() => seen.push(controller.version()));

    wait(1000);
    controller.tick();
    expect(seen).toEqual([]);
    wait(10 * MIN); // asleep
    controller.tick();
    expect(seen).toHaveLength(1);
    expect(controller.snapshot()?.away).not.toBeNull();

    await controller.resolveAway("end");
    expect(controller.state().status).toBe("reflecting");
  });

  it("starts a session for a planned block, and never loses it if the block was refused", async () => {
    const server = fakeSessionServer();
    server.refuseBlock("stale");
    const controller = world().page();
    await controller.restore();

    await controller.start({ ...META, planBlockId: "stale" });

    // Sent once with the block (refused), then once without it.
    const starts = server.calls.filter((c) => c.method === "POST" && c.path === "/sessions");
    expect(starts.map((c) => (c.body as { plan_block_id?: string | null }).plan_block_id)).toEqual([
      "stale",
      null,
    ]);
    expect(controller.state()).toMatchObject({ status: "open" });
    expect(controller.snapshot()).toMatchObject({ sessionId: "server-1", planUnlinked: true });
    expect(controller.problems()).toEqual([]);
    expect(server.only().plan_block_id).toBeNull();
  });

  it("keeps a planned block that the server accepts", async () => {
    const server = fakeSessionServer();
    const controller = world().page();
    await controller.restore();

    await controller.start({ ...META, planBlockId: "b1" });

    expect(server.only().plan_block_id).toBe("b1");
    expect(controller.snapshot()).toMatchObject({ planUnlinked: false });
  });
});
