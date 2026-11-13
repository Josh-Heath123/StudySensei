/**
 * When the open session's page was last seen alive. Recorded every 15 s while a
 * session is open, so a later page load can tell how long the student was away
 * (a closed tab, a crash, a laptop that slept).
 */
import { readJson, writeJson, type KeyValueStore } from "./store";

const KEY = "studysensei.session.lastActive";

type Beat = { startId: string; at: number };

export const HEARTBEAT_MS = 15_000;

export function recordActive(store: KeyValueStore, startId: string, at: number): void {
  writeJson(store, KEY, { startId, at } satisfies Beat);
}

/** The last-seen time for this session, or null if none was recorded here. */
export function lastActive(store: KeyValueStore, startId: string): number | null {
  const beat = readJson<Partial<Beat> | null>(store, KEY, null);
  return beat?.startId === startId && typeof beat.at === "number" ? beat.at : null;
}

export function clearActive(store: KeyValueStore): void {
  store.removeItem(KEY);
}
