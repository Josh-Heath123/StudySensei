import { Link } from "react-router";

import { Button } from "@/ui/button";

import { NO_PLAN_YET } from "./copy";

const FIRST_HOUR = 8;
const LAST_HOUR = 20;
const ROW_PX = 52;

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * docs/DESIGN.md "Day timeline": hour rows with a NOW marker. The planner (Phase 4)
 * adds the study blocks; until then the grid says the plan isn't there yet rather
 * than showing made-up blocks.
 */
export function DayTimeline({ now }: { now: Date }) {
  const hours = Array.from({ length: LAST_HOUR - FIRST_HOUR }, (_, i) => FIRST_HOUR + i);
  const minutesIn = (now.getHours() - FIRST_HOUR) * 60 + now.getMinutes();
  const showNow = minutesIn >= 0 && minutesIn < (LAST_HOUR - FIRST_HOUR) * 60;

  return (
    <section aria-labelledby="day-heading" className="mb-8">
      <h2 id="day-heading" className="type-h3 mb-3">
        Your day
      </h2>
      <div className="relative">
        <ol aria-hidden className="text-muted text-xs">
          {hours.map((hour) => (
            <li key={hour} className="border-line tabular border-t pt-1" style={{ height: ROW_PX }}>
              {pad(hour)}:00
            </li>
          ))}
        </ol>
        {showNow && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 flex items-center gap-2"
            style={{ top: (minutesIn / 60) * ROW_PX }}
          >
            <span className="bg-ink text-paper rounded-sm px-1.5 py-0.5 text-xs font-semibold">
              NOW
            </span>
            <span className="bg-ink h-0.5 flex-1" />
          </div>
        )}
        <div className="absolute inset-x-12 top-6 sm:inset-x-16">
          <div className="border-line bg-paper rounded-lg border-2 p-5">
            <p>{NO_PLAN_YET}</p>
            <Button asChild variant="outline" size="sm" className="mt-3">
              <Link to="/modules">Add deadlines</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
