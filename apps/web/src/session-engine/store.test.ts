import { clearActive, lastActive, recordActive } from "./heartbeat";
import { browserStore, memoryStore, readJson, writeJson } from "./store";

describe("readJson / writeJson", () => {
  it("round-trips a value", () => {
    const store = memoryStore();
    writeJson(store, "k", { a: 1 });

    expect(readJson(store, "k", null)).toEqual({ a: 1 });
  });

  it("falls back on a missing or corrupt value", () => {
    const store = memoryStore();
    store.setItem("bad", "{not json");

    expect(readJson(store, "missing", [])).toEqual([]);
    expect(readJson(store, "bad", [])).toEqual([]);
  });
});

describe("browserStore", () => {
  it("uses localStorage", () => {
    const store = browserStore();
    store.setItem("studysensei.test", "1");

    expect(localStorage.getItem("studysensei.test")).toBe("1");
    store.removeItem("studysensei.test");
    expect(localStorage.getItem("studysensei.test")).toBeNull();
  });

  it("keeps working in memory when localStorage throws (private mode, quota)", () => {
    const broken = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: () => {
        throw new Error("SecurityError");
      },
    };
    vi.stubGlobal("localStorage", broken);
    const store = browserStore();

    store.setItem("k", "v");
    expect(store.getItem("k")).toBe("v");
    store.removeItem("k");
    expect(store.getItem("k")).toBeNull();
  });
});

describe("heartbeat", () => {
  it("remembers when the open session was last seen", () => {
    const store = memoryStore();
    recordActive(store, "start-1", 1000);
    recordActive(store, "start-1", 16_000);

    expect(lastActive(store, "start-1")).toBe(16_000);
  });

  it("belongs to one session", () => {
    const store = memoryStore();
    recordActive(store, "start-1", 1000);

    expect(lastActive(store, "start-2")).toBeNull();
    clearActive(store);
    expect(lastActive(store, "start-1")).toBeNull();
  });
});
