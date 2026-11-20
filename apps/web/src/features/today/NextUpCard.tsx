import { Play } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useNextBlock, useSkipBlock, type PlanBlock } from "@/features/plan/api";
import { blockName, isNow } from "@/features/plan/planText";
import { clock, dayLabel, zoned } from "@/features/plan/week";
import { hasSessionInProgress, useSession } from "@/features/session/session";
import { StartSessionButton } from "@/features/session/StartSessionButton";
import { usePlanningSettings } from "@/features/settings/api";
import { useNow } from "@/lib/useNow";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";

/**
 * docs/DESIGN.md "Screens: Today": the hero. The signature gradient is its background and
 * every word sits on the inner `glass-hero` layer, never on the gradient itself. It names the
 * plan's next block (GET /plan/next): what, when, how (the method) and why, with Start and Skip
 * only when the server says they're possible.
 */
export function NextUpCard() {
  const next = useNextBlock();
  const settings = usePlanningSettings();
  const timeZone = settings.data?.timezone ?? null;
  const block = next.data ?? null;
  return (
    <section
      aria-labelledby="next-up-heading"
      className="rounded-xl bg-[image:var(--gradient)] p-3 shadow-md sm:p-4"
    >
      <div className="glass-hero rounded-lg p-6 sm:p-7">
        <p className="type-label text-muted mb-3">Next up</p>
        {block && timeZone ? (
          <NextBlock block={block} timeZone={timeZone} />
        ) : (
          <>
            <h2 id="next-up-heading" className="type-h2">
              Nothing planned yet
            </h2>
            <p className="text-muted mt-2">
              <Link to="/settings" className="text-link hover:underline">
                Add study time
              </Link>{" "}
              and{" "}
              <Link to="/modules" className="text-link hover:underline">
                an assessment
              </Link>{" "}
              for a plan, or start a session on any module.
            </p>
            <div className="mt-6">
              <StartSessionButton />
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function NextBlock({ block, timeZone }: { block: PlanBlock; timeZone: string }) {
  const controller = useSession();
  const navigate = useNavigate();
  const skip = useSkipBlock();
  const [confirmSkip, setConfirmSkip] = useState(false);
  const now = useNow(30_000).getTime();
  const start = zoned(block.start, timeZone);
  const today = zoned(now, timeZone).date;
  const live = isNow(block, now);
  const when = live
    ? "Now"
    : start.date === today
      ? `Today, ${clock(start.minutes)}`
      : `${dayLabel(start.date)}, ${clock(start.minutes)}`;

  function startSession() {
    void controller.start({
      moduleId: block.module_id,
      topicId: block.topic_id,
      planBlockId: block.id,
    });
    void navigate("/session");
  }

  return (
    <>
      <h2 id="next-up-heading" className="type-h2">
        {blockName(block)}
      </h2>
      <p className="text-muted mt-1 text-sm tabular-nums">
        <span className={live ? "text-link font-semibold" : undefined}>{when}</span> ·{" "}
        {block.minutes} min · {block.module_code} {block.assessment_title}
      </p>
      <p className="mt-4">{block.method_text}</p>
      <p className="text-muted mt-2 text-sm">
        <span className="text-fg font-medium">Why: </span>
        {block.reason_text}
      </p>
      <div className="mt-6 flex flex-wrap gap-2">
        {block.actions.start ? (
          <Button variant="module" onClick={startSession}>
            <Play aria-hidden /> Start session
          </Button>
        ) : (
          hasSessionInProgress(controller) && <StartSessionButton />
        )}
        {block.actions.skip && (
          <Button variant="outline" onClick={() => setConfirmSkip(true)}>
            Skip
          </Button>
        )}
      </div>
      <ConfirmDialog
        open={confirmSkip}
        onOpenChange={setConfirmSkip}
        title="Skip this block?"
        description={`${blockName(block)}, ${when}. Its time is placed again if there's room.`}
        confirmLabel="Skip"
        busyLabel="Skipping…"
        onConfirm={() => skip.mutateAsync(block.id)}
      />
    </>
  );
}
