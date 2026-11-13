/** The subset of the Storage API the session engine needs (localStorage fits it). */
export type KeyValueStore = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

/** An in-memory store: for tests, and as the fallback when localStorage is unusable. */
export function memoryStore(): KeyValueStore {
  const items = new Map<string, string>();
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => void items.set(key, value),
    removeItem: (key) => void items.delete(key),
  };
}

/**
 * localStorage, wrapped so it never throws. In private mode or when the quota is
 * full, values are kept in memory instead: the session keeps working in this tab,
 * it just won't survive a reload.
 */
export function browserStore(): KeyValueStore {
  const fallback = memoryStore();
  const attempt = <T>(action: (storage: Storage) => T, otherwise: () => T): T => {
    try {
      return action(globalThis.localStorage);
    } catch {
      return otherwise();
    }
  };
  return {
    getItem: (key) =>
      attempt(
        (s) => s.getItem(key) ?? fallback.getItem(key),
        () => fallback.getItem(key),
      ),
    setItem: (key, value) =>
      attempt(
        (s) => {
          s.setItem(key, value);
          fallback.removeItem(key);
        },
        () => fallback.setItem(key, value),
      ),
    removeItem: (key) => {
      fallback.removeItem(key);
      attempt(
        (s) => s.removeItem(key),
        () => undefined,
      );
    },
  };
}

/** Parse a stored JSON value, or return `fallback` if it's missing or unreadable. */
export function readJson<T>(store: KeyValueStore, key: string, fallback: T): T {
  const raw = store.getItem(key);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJson(store: KeyValueStore, key: string, value: unknown): void {
  store.setItem(key, JSON.stringify(value));
}
