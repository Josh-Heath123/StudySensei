import { CalendarDays } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/ui/button";

import { NO_PLAN_YET } from "./copy";

/**
 * The day on a solid card. The planner (Phase 4) will supply the day's study blocks; until it
 * exists there are none, so the day is a compact empty state that says so honestly, rather
 * than ~1,000 px of empty hour rows on a phone. (The old hour grid is in git history; the
 * planner will draw its own.)
 */
export function DayTimeline() {
  return (
    <section aria-labelledby="day-heading" className="surface-card rounded-xl p-5 sm:p-6">
      <h2 id="day-heading" className="type-h3 mb-4">
        Your day
      </h2>
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
            <Link to="/modules">Add deadlines</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
