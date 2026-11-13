import { createContext, use, useEffect, useSyncExternalStore } from "react";

import { createSessionEngine } from "@/session-engine/engine";
import { browserStore } from "@/session-engine/store";

import { fetchActiveSession } from "./api";
import { createSessionController, type SessionController } from "./controller";

/** The real thing: the browser's clock, UUIDs and localStorage. */
export function createBrowserController(): SessionController {
  const store = browserStore();
  const engine = createSessionEngine({
    now: () => Date.now(),
    newId: () => crypto.randomUUID(),
    store,
  });
  return createSessionController({ engine, store, fetchActive: fetchActiveSession });
}

export const SessionContext = createContext<SessionController | null>(null);

/**
 * The app's one session controller. Re-renders when its state changes (not on
 * every second: the running screen redraws itself), and restores the open
 * session the first time any component asks.
 */
export function useSession(): SessionController {
  const controller = use(SessionContext);
  if (controller === null) throw new Error("useSession needs a <SessionProvider>");
  useSyncExternalStore(controller.subscribe, controller.version);
  useEffect(() => {
    void controller.restore();
  }, [controller]);
  return controller;
}

/** Whether a session is open or waiting for its reflection (so Start means Return). */
export function hasSessionInProgress(controller: SessionController): boolean {
  const { status } = controller.state();
  return status === "open" || status === "reflecting";
}
