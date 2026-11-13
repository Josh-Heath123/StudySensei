import { useEffect, useState } from "react";

import type { SessionController } from "./controller";

/** How often to try again while events are queued and nothing else prompts a flush. */
const RETRY_EVERY_TICKS = 30;

/**
 * Redraw the running session every `intervalMs`. Each redraw calls `tick()` (the
 * heartbeat and the away check); the time itself always comes from event
 * timestamps, so a throttled background tab can't make it drift. Queued events
 * are sent when the browser comes back online or the tab becomes visible again.
 */
export function useSessionClock(controller: SessionController, intervalMs = 1000): void {
  const [, setFrame] = useState(0);
  useEffect(() => {
    let ticks = 0;
    const redraw = () => {
      controller.tick();
      setFrame((frame) => frame + 1);
    };
    const resync = () => {
      redraw();
      void controller.flush();
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") resync();
    };
    const id = setInterval(() => {
      redraw();
      ticks += 1;
      if (ticks % RETRY_EVERY_TICKS === 0 && controller.sync() !== "synced") {
        void controller.flush();
      }
    }, intervalMs);
    window.addEventListener("online", resync);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      window.removeEventListener("online", resync);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [controller, intervalMs]);
}

/** Show `title` in the browser tab while mounted, then put the old one back. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    return () => {
      document.title = previous;
    };
  }, []);
  useEffect(() => {
    document.title = title;
  }, [title]);
}
