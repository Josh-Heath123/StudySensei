import { cn } from "@/lib/utils";
import { ModuleBadge } from "@/ui/module-badge";

import { useModules } from "../modules/api";
import { useUpcomingAssessments } from "./api";
import { countdowns, type Countdown } from "./deadlines";

const tileDate = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
});

/** Days to the next assessments, from the real deadlines: calm, solid tiles. */
export function CountdownTiles({ now }: { now: Date }) {
  const modules = useModules();
  const assessments = useUpcomingAssessments();
  if (!modules.data || !assessments.data) return null;

  const tiles = countdowns(assessments.data, modules.data, now);
  if (tiles.length === 0) return null;
  return (
    <ul aria-label="Countdowns" className="flex flex-wrap gap-3">
      {tiles.map((tile, i) => (
        <CountdownTile key={tile.id} tile={tile} nearest={i === 0} />
      ))}
    </ul>
  );
}

function CountdownTile({ tile, nearest }: { tile: Countdown; nearest: boolean }) {
  const label =
    tile.days === 0
      ? `due today: ${tile.title}`
      : `${tile.days === 1 ? "day" : "days"} to ${tile.title}`;
  return (
    // The nearest deadline gets a violet hairline (an outline, so it doesn't fight the
    // card's border and shadow) and the raised shadow.
    <li
      data-nearest={nearest}
      className={cn(
        "surface-card grid w-40 content-start gap-2 rounded-xl p-4 sm:w-44 sm:p-5",
        nearest && "outline-primary-edge shadow-md outline-1 -outline-offset-1",
      )}
    >
      <span className="type-countdown">{tile.days}</span>
      <span className="text-sm font-semibold">{label}</span>
      <span className="text-muted flex flex-wrap items-center gap-2 text-sm">
        <ModuleBadge colour={tile.module.colour} className="px-1.5 py-0.5 text-xs">
          {tile.module.code}
        </ModuleBadge>
        <time dateTime={tile.dueAt}>{tileDate.format(new Date(tile.dueAt))}</time>
      </span>
    </li>
  );
}
