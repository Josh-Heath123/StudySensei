import { fakeSessionServer } from "@/test/fakeSessionServer";

import { createSessionEngine, type SessionEngine } from "./engine";
import { lastActive } from "./heartbeat";
import { pendingEvents } from "./outbox";
import { memoryStore, type KeyValueStore } from "./store";
import { TimelineError } from "./timer";

const SEC = 1000;
const MIN = 60 * SEC;
const T0 = Date.parse("2026-11-13T08:00:00.000Z");

/** A fake clock and id source shared by every "page load" in a test. */
function world() {
  let t = T0;
  let n = 0;
  const store = memoryStore();
  const clock = {
    now: () => t,
    /** Move time on without the page noticing (sleep, closed tab). */
    jump: (ms: number) => {
      t += ms;
    },
  };
  const page = (s: KeyValueStore = store) =>
    createSessionEngine({ now: clock.now, newId: () => `id-${++n}`, store: s });
  return { store, clock, page };
}

/** Let the page run normally for `ms`, ticking once a second like a display would. */
function run(engine: SessionEngine, clock: { jump: (ms: number) => void }, ms: number) {
  for (let i = 0; i < ms / SEC; i++) {
    clock.jump(SEC);
    expect(engine.tick()).toBeNull();
  }
}

describe("session engine", () => {
  it("does pause and resume arithmetic from event times", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const engine = page();

    await engine.start("module-1");
    run(engine, clock, 10 * MIN);
    await engine.pause();
    run(engine, clock, 5 * MIN);
    await engine.resume();
    run(engine, clock, 20 * MIN);

    expect(engine.snapshot()?.totals).toEqual({ activeMs: 30 * MIN, breakMs: 0 });
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "pause", "resume"]);
  });

  it("only redraws on ticks: time comes from the clock, not from counting ticks", async () => {
    fakeSessionServer();
    const { clock, page } = world();
    const engine = page();
    await engine.start("module-1");

    clock.jump(90 * SEC); // a throttled background tab: no ticks at all for 90 s

    expect(engine.snapshot()?.totals.activeMs).toBe(90 * SEC);
  });

  it("shows a break as due without starting one, and times the break", async () => {
    fakeSessionServer();
    const { clock, page } = world();
    const engine = page();
    await engine.start("module-1");

    run(engine, clock, 55 * MIN);
    expect(engine.snapshot()).toMatchObject({
      state: "active",
      cycle: { phase: "focus", breakDue: true },
    });

    await engine.breakStart();
    run(engine, clock, 12 * MIN);
    expect(engine.snapshot()?.cycle).toEqual({
      phase: "break",
      breakElapsedMs: 12 * MIN,
      breakRemainingMs: 0,
      breakOverByMs: 2 * MIN,
    });

    await engine.breakEnd();
    run(engine, clock, 5 * MIN);
    expect(engine.snapshot()).toMatchObject({
      totals: { activeMs: 60 * MIN, breakMs: 12 * MIN },
      cycle: { phase: "focus", focusMs: 5 * MIN, breakDue: false },
    });
  });

  it("refuses an impossible command and records nothing", async () => {
    const server = fakeSessionServer();
    const { store, page } = world();
    const engine = page();
    await engine.start("module-1");

    await expect(engine.resume()).rejects.toThrow(TimelineError);
    expect(engine.canRecord("resume")).toBe(false);
    expect(engine.canRecord("pause")).toBe(true);
    expect(server.only().events).toHaveLength(1);
    expect(pendingEvents(store, engine.snapshot()!.startId)).toEqual([]);
  });

  it("resumes after a reload mid-session, including events still queued offline", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const before = page();
    await before.start("module-1", "topic-1");
    run(before, clock, 25 * MIN);
    await before.breakStart();
    run(before, clock, 5 * MIN);
    server.setMode("offline");
    await before.breakEnd(); // queued, not on the server yet
    run(before, clock, 10 * MIN);
    const shown = before.snapshot();

    clock.jump(20 * SEC); // the reload itself
    const after = page();
    const prompt = after.restore(server.only());

    expect(prompt).toBeNull();
    expect(after.snapshot()).toMatchObject({
      state: "active",
      startId: shown?.startId,
      sessionId: "server-1",
      totals: { activeMs: 35 * MIN + 20 * SEC, breakMs: 5 * MIN },
    });
    server.setMode("online");
    await after.flush();
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "break_start", "break_end"]);
  });

  it("restores a session started offline from the queue alone", async () => {
    const server = fakeSessionServer();
    server.setMode("offline");
    const { clock, page } = world();
    const before = page();
    await before.start("module-1");
    run(before, clock, 10 * MIN);
    await before.pause();

    const after = page();
    expect(after.restore(null)).toBeNull(); // the server has no open session yet
    expect(after.snapshot()).toMatchObject({ state: "paused", sessionId: null });

    server.setMode("online");
    await after.flush();
    expect(after.snapshot()?.sessionId).toBe("server-1");
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "pause"]);
  });

  it("asks after a laptop sleep, and stopping the clock pauses when you left", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const engine = page();
    await engine.start("module-1");
    run(engine, clock, 10 * MIN);

    clock.jump(3 * 60 * MIN + 12 * MIN); // asleep: no ticks
    const prompt = engine.tick();

    expect(prompt).toMatchObject({ since: T0 + 10 * MIN, awayMs: 192 * MIN });
    expect(prompt?.message).toBe(
      "You were away for 3 h 12 min. Keep that time, or stop the clock when you left?",
    );
    expect(engine.tick()).toEqual(prompt); // it keeps asking until answered

    await engine.resolveAway("pause");

    expect(engine.snapshot()).toMatchObject({
      state: "paused",
      away: null,
      totals: { activeMs: 10 * MIN, breakMs: 0 },
    });
    const pause = server.only().events.at(-1);
    expect(pause).toMatchObject({
      type: "pause",
      occurred_at: new Date(T0 + 10 * MIN).toISOString(),
    });
  });

  it("asks after a sleep during a break, and stopping the clock ends the break when you left", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const engine = page();
    await engine.start("module-1");
    run(engine, clock, 50 * MIN);
    await engine.breakStart();
    run(engine, clock, 3 * MIN);

    clock.jump(2 * 60 * MIN);
    expect(engine.tick()).not.toBeNull();
    await engine.resolveAway("pause");

    expect(engine.snapshot()).toMatchObject({
      state: "paused",
      totals: { activeMs: 50 * MIN, breakMs: 3 * MIN },
    });
    expect(server.only().events.map((e) => e.type)).toEqual([
      "start",
      "break_start",
      "break_end",
      "pause",
    ]);
  });

  it("asks when a closed tab is reopened hours later; 'keep' counts the time", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const before = page();
    await before.start("module-1");
    run(before, clock, 20 * MIN); // tab closed after this

    clock.jump(3 * 60 * MIN);
    const after = page();
    const prompt = after.restore(server.only());

    expect(prompt).toMatchObject({ since: T0 + 20 * MIN, awayMs: 180 * MIN });
    expect(prompt?.message).toContain("away for 3 h.");
    await after.resolveAway("keep");
    expect(after.snapshot()).toMatchObject({ away: null, totals: { activeMs: 200 * MIN } });
    expect(server.only().events).toHaveLength(1);
  });

  it("can end a closed-tab session at the time you left", async () => {
    const server = fakeSessionServer();
    const { store, clock, page } = world();
    const before = page();
    await before.start("module-1");
    run(before, clock, 20 * MIN);

    clock.jump(3 * 60 * MIN);
    const after = page();
    after.restore(server.only());
    await after.resolveAway("end");

    expect(after.snapshot()).toMatchObject({
      state: "ended",
      totals: { activeMs: 20 * MIN, breakMs: 0 },
    });
    expect(server.only().events.at(-1)).toMatchObject({
      type: "end",
      occurred_at: new Date(T0 + 20 * MIN).toISOString(),
    });
    expect(lastActive(store, after.snapshot()!.startId)).toBeNull();
  });

  it("asks again after another reload if the question wasn't answered", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const first = page();
    await first.start("module-1");
    run(first, clock, 5 * MIN);
    clock.jump(60 * MIN);
    expect(page().restore(server.only())).not.toBeNull();

    clock.jump(30 * SEC);

    expect(page().restore(server.only())).toMatchObject({ since: T0 + 5 * MIN });
  });

  it("doesn't ask after a quick reload, or when the clock was paused", async () => {
    const server = fakeSessionServer();
    const { clock, page } = world();
    const first = page();
    await first.start("module-1");
    run(first, clock, 5 * MIN);

    clock.jump(30 * SEC);
    const second = page();
    expect(second.restore(server.only())).toBeNull();

    await second.pause();
    clock.jump(5 * 60 * MIN);
    expect(page().restore(server.only())).toBeNull();
  });

  it("restores nothing when there's no open session anywhere", () => {
    fakeSessionServer();
    const { page } = world();
    const engine = page();

    expect(engine.restore(null)).toBeNull();
    expect(engine.snapshot()).toBeNull();
    expect(engine.canRecord("start")).toBe(true);
  });

  it("counts the recorded events, for the summary's sample size", async () => {
    fakeSessionServer();
    const { clock, page } = world();
    const engine = page();
    await engine.start("module-1");
    run(engine, clock, 5 * MIN);
    await engine.pause();
    await engine.resume();

    expect(engine.snapshot()?.eventCount).toBe(3);
  });

  it("keeps the server id after an ended session is synced and forgotten", async () => {
    const server = fakeSessionServer();
    server.setMode("offline");
    const { store, clock, page } = world();
    const engine = page();
    await engine.start("module-1");
    run(engine, clock, 5 * MIN);
    await engine.end();
    expect(engine.snapshot()?.sessionId).toBeNull();

    server.setMode("online");
    await engine.flush();

    expect(engine.snapshot()).toMatchObject({ state: "ended", sessionId: "server-1" });
    expect(pendingEvents(store, engine.snapshot()!.startId)).toEqual([]);
  });

  it("doesn't start a second session while one is open", async () => {
    fakeSessionServer();
    const { page } = world();
    const engine = page();
    await engine.start("module-1");

    await expect(engine.start("module-1")).rejects.toThrow(TimelineError);
  });

  it("sends a planned block with the start, and drops it once if the block is refused", async () => {
    const server = fakeSessionServer();
    server.refuseBlock("b-old");
    const { clock, page } = world();
    const engine = page();

    await engine.start("module-1", "topic-1", "b-old");
    run(engine, clock, 5 * MIN);
    await engine.end();

    // The session is kept, unlinked, with every event.
    expect(server.only().plan_block_id).toBeNull();
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "end"]);
    expect(engine.snapshot()).toMatchObject({ planUnlinked: true, state: "ended" });
  });

  it("queues a planned block offline and sends it with the start later", async () => {
    const server = fakeSessionServer();
    server.setMode("offline");
    const { page } = world();
    const engine = page();

    await engine.start("module-1", null, "b1");
    server.setMode("online");
    await engine.flush();

    expect(server.only().plan_block_id).toBe("b1");
    expect(engine.snapshot()?.planUnlinked).toBe(false);
  });
});
