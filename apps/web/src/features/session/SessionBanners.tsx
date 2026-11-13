import type { ReactNode } from "react";

import type { Snapshot } from "@/session-engine/engine";
import type { CyclePlan } from "@/session-engine/timer";
import { Button } from "@/ui/button";

import type { SessionController } from "./controller";

/** A calm, in-page notice. Nothing here blocks the screen. */
function Banner({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div
      role="status"
      className="border-line flex flex-wrap items-center justify-between gap-3 rounded-lg border-2 px-4 py-3"
    >
      <p className="text-sm">{children}</p>
      {action}
    </div>
  );
}

export function SessionBanners({
  controller,
  snapshot,
  plan,
}: {
  controller: SessionController;
  snapshot: Snapshot;
  plan: CyclePlan;
}) {
  const sync = controller.sync();
  const problems = controller.problems();
  const breakDue =
    snapshot.state === "active" && snapshot.cycle.phase === "focus" && snapshot.cycle.breakDue;

  if (!breakDue && sync === "synced" && problems.length === 0) return null;
  return (
    <div className="grid gap-3">
      {breakDue && (
        <Banner>
          <strong>Break due.</strong> You&apos;ve focused for {plan.focusMin} min. Take a break when
          you reach a good stopping point.
        </Banner>
      )}
      {sync === "offline" && (
        <Banner>
          <strong>Offline.</strong> Your changes are saved on this device and will be sent when
          you&apos;re back online.
        </Banner>
      )}
      {sync === "retry" && (
        <Banner>
          <strong>The server didn&apos;t answer.</strong> Your changes are saved on this device and
          will be sent again shortly.
        </Banner>
      )}
      {problems.length > 0 && (
        <Banner
          action={
            <Button variant="quiet" onClick={() => controller.dismissProblems()}>
              Dismiss
            </Button>
          }
        >
          <strong>Not saved:</strong> {problems.join(" ")}
        </Banner>
      )}
    </div>
  );
}
