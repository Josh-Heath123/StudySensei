import { useState } from "react";

import type { AvailabilityException } from "@/features/settings/api";
import { cn } from "@/lib/utils";

import type { PlanBlock } from "./api";
import { BlockPopover } from "./BlockPopover";
import { DayMenu } from "./DayMenu";
import { PlanBlockCard } from "./PlanBlockCard";
import { clock, dayLabel, zoned, type Span } from "./week";

type Props = {
  blocks: PlanBlock[];
  week: string[];
  today: string;
  timeZone: string;
  now: number;
  freeByDate: Record<string, Span[]>;
  unavailable: Set<string>;
  exceptions: Record<string, AvailabilityException>;
};

/**
 * Below 1024 px: the week as a list by day, with the same cards and day menus, and no
 * dragging (Move… in a block's sheet does it). In the current week it starts at today:
 * earlier days fold under "Earlier this week", shown only when they have blocks, and a past
 * day has no menu (decision 0023).
 */
export function Agenda({
  blocks,
  week,
  today,
  timeZone,
  now,
  freeByDate,
  unavailable,
  exceptions,
}: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const onDay = (date: string) => blocks.filter((b) => zoned(b.start, timeZone).date === date);
  const thisWeek = week.includes(today);
  const earlier = thisWeek ? week.filter((date) => date < today && onDay(date).length > 0) : [];
  const shown = thisWeek ? week.filter((date) => date >= today) : week;

  const day = (date: string) => {
    const dayBlocks = onDay(date);
    const free = freeByDate[date] ?? [];
    const off = unavailable.has(date);
    return (
      <li key={date} className="surface-card rounded-xl p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className={cn("type-h3", date === today && "text-link")}>
              {dayLabel(date)}
              {date === today && <span className="text-muted ml-2 text-sm">Today</span>}
            </h2>
            <p className="text-muted text-xs tabular-nums">
              {off
                ? "Unavailable"
                : free.length > 0
                  ? `Free ${free.map((s) => `${clock(s.start)}–${clock(s.end)}`).join(", ")}`
                  : "No study time"}
            </p>
          </div>
          {date >= today && <DayMenu date={date} unavailable={off} exception={exceptions[date]} />}
        </div>
        {dayBlocks.length === 0 ? (
          <p className="text-muted text-sm">Nothing planned.</p>
        ) : (
          <ul className="grid gap-2">
            {dayBlocks.map((block) => (
              <li key={block.id}>
                <BlockPopover
                  block={block}
                  timeZone={timeZone}
                  week={week}
                  freeByDate={freeByDate}
                  open={openId === block.id}
                  onOpenChange={(open) => setOpenId(open ? block.id : null)}
                >
                  <PlanBlockCard block={block} timeZone={timeZone} now={now} />
                </BlockPopover>
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div className="grid gap-4">
      {earlier.length > 0 && (
        <details data-testid="agenda-earlier">
          <summary className="text-link cursor-pointer text-sm font-medium">
            Earlier this week
          </summary>
          <ol className="mt-3 grid gap-4">{earlier.map(day)}</ol>
        </details>
      )}
      <ol className="grid gap-4" data-testid="agenda">
        {shown.map(day)}
      </ol>
    </div>
  );
}
