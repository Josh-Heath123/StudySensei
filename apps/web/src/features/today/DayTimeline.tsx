import { CalendarDays } from "lucide-react";
import { Link } from "react-router";

import { usePlan } from "@/features/plan/api";
import { blockTitle, isNow, measuredText, METHOD_LABELS } from "@/features/plan/planText";
import { clock, zoned } from "@/features/plan/week";
import { usePlanningSettings } from "@/features/settings/api";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

import { NO_PLAN_YET } from "./copy";

/**
 * "Your day" on a solid card: today's blocks from the plan (GET /plan for today), compact,
 * each with its status. With none, a compact empty state.
 */
export function DayTimeline() {
  const settings = usePlanningSettings();
  const timeZone = settings.data?.timezone ?? null;
  const now = useNow(30_000).getTime();
  const today = timeZone ? zoned(now, timeZone).date : null;
  const plan = usePlan(today, today);
  const blocks =
    plan.data?.blocks.filter((b) => timeZone && zoned(b.start, timeZone).date === today) ?? [];

  return (
    <section aria-labelledby="day-heading" className="surface-card rounded-xl p-5 sm:p-6">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h2 id="day-heading" className="type-h3">
          Your day
        </h2>
        {blocks.length > 0 && (
          <Link to="/plan" className="text-link text-sm hover:underline">
            Week
          </Link>
        )}
      </div>
      {blocks.length > 0 && timeZone ? (
        <ol className="grid grid-cols-[minmax(0,1fr)] gap-2">
          {blocks.map((block) => {
            const start = zoned(block.start, timeZone);
            const end = zoned(block.end, timeZone);
            const live = isNow(block, now);
            const quiet = block.status === "skipped" || block.status === "missed";
            return (
              <li
                key={block.id}
                className={cn(
                  "border-line flex min-w-0 items-center gap-3 rounded-md border border-l-4 px-3 py-2",
                  quiet && "text-muted",
                )}
                style={{ borderLeftColor: block.module_colour }}
              >
                <span className="text-muted w-24 shrink-0 text-sm tabular-nums">
                  {clock(start.minutes)}–{clock(end.minutes)}
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      "block truncate text-sm font-medium",
                      block.status === "skipped" && "line-through",
                    )}
                  >
                    {blockTitle(block)}
                  </span>
                  <span className="text-muted text-xs">{METHOD_LABELS[block.method]}</span>
                </span>
                <span className="shrink-0 text-xs font-semibold">
                  {live && <span className="text-link">Now</span>}
                  {block.status === "done" && (
                    <span className="text-success">{measuredText(block) ?? "Done"}</span>
                  )}
                  {block.status === "missed" && "Missed"}
                  {block.status === "skipped" && "Skipped"}
                </span>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="flex items-start gap-4">
          <span
            aria-hidden
            className="bg-accent-soft text-link grid size-11 shrink-0 place-items-center rounded-lg"
          >
            <CalendarDays className="size-5" />
          </span>
          <div className="grid min-w-0 gap-3">
            <p className="text-muted">{NO_PLAN_YET}</p>
            <Button asChild variant="outline" size="sm" className="justify-self-start">
              <Link to="/plan">Open the plan</Link>
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
