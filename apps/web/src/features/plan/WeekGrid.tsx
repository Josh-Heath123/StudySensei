import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import type { AvailabilityException } from "@/features/settings/api";
import { cn } from "@/lib/utils";

import { useMoveBlock, type PlanBlock } from "./api";
import { BlockPopover } from "./BlockPopover";
import { DayMenu } from "./DayMenu";
import { PlanBlockCard } from "./PlanBlockCard";
import { clock, dayLabel, fromZoned, hourRange, snap5, zoned, type Span } from "./week";

/** Pixels per minute: a 50-minute block is 55 px tall. */
export const PX_PER_MINUTE = 1.1;
const DRAG_THRESHOLD_PX = 4;

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

type Drag = {
  block: PlanBlock;
  pointerId: number;
  x0: number;
  y0: number;
  /** Minutes from the block's start to where it was grabbed. */
  grab: number;
  date: string;
  minutes: number;
  moved: boolean;
};

/** Where a block is placed while it waits for the server (after a drop). */
type Placed = { blockId: string; date: string; minutes: number };

/**
 * docs/DESIGN.md "Week grid" (from 1024 px): seven days, Monday first, in the user's
 * timezone; hour rows only from the week's earliest window or block to its latest; free
 * windows as subtle bands; blocks as cards. Blocks the server says can move can be dragged
 * (pointer events, snapping to 5 minutes, across days); the server checks every drop, and a
 * refused one snaps back with its sentence beside the block. Move… in the popover is the
 * keyboard path.
 */
export function WeekGrid({
  blocks,
  week,
  today,
  timeZone,
  now,
  freeByDate,
  unavailable,
  exceptions,
}: Props) {
  const move = useMoveBlock();
  const columns = useRef<(HTMLDivElement | null)[]>([]);
  // The drag lives in a ref, so pointer events between renders see the latest one (a fast
  // flick is one pointermove then pointerup at once); the state only re-renders the ghost.
  const dragRef = useRef<Drag | null>(null);
  const [drag, setDragState] = useState<Drag | null>(null);
  const setDrag = (next: Drag | null) => {
    dragRef.current = next;
    setDragState(next);
  };
  const [placed, setPlaced] = useState<Placed | null>(null);
  const [problem, setProblem] = useState<{ blockId: string; text: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const justDragged = useRef(false);

  useEffect(() => {
    if (problem === null) return;
    const timer = window.setTimeout(() => setProblem(null), 8000);
    return () => window.clearTimeout(timer);
  }, [problem]);

  const placedBlocks = blocks
    .map((block) => ({
      block,
      start: zoned(block.start, timeZone),
      end: zoned(block.end, timeZone),
    }))
    .filter(({ start }) => week.includes(start.date));
  const spans: Span[] = [
    ...week.flatMap((date) => freeByDate[date] ?? []),
    ...placedBlocks.map(({ start, end }) => ({
      date: start.date,
      start: start.minutes,
      end: end.date === start.date ? end.minutes : 24 * 60,
    })),
  ];
  const range = hourRange(spans) ?? { first: 8, last: 20 };
  const top = range.first * 60;
  const height = (range.last - range.first) * 60 * PX_PER_MINUTE;
  const hours = Array.from({ length: range.last - range.first + 1 }, (_, i) => range.first + i);

  function target(event: ReactPointerEvent, current: Drag): { date: string; minutes: number } {
    const index = columns.current.findIndex((column) => {
      if (!column) return false;
      const rect = column.getBoundingClientRect();
      return event.clientX >= rect.left && event.clientX < rect.right;
    });
    const column = index >= 0 ? columns.current[index] : null;
    const date = index >= 0 ? week[index]! : current.date;
    const rect = (column ?? columns.current[week.indexOf(current.date)])?.getBoundingClientRect();
    if (!rect) return { date, minutes: current.minutes };
    const raw = top + (event.clientY - rect.top) / PX_PER_MINUTE - current.grab;
    const minutes = Math.min(Math.max(snap5(raw), top), range.last * 60 - current.block.minutes);
    return { date, minutes };
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>, block: PlanBlock) {
    if (!block.actions.move || event.button !== 0 || move.isPending) return;
    const start = zoned(block.start, timeZone);
    const rect = event.currentTarget.getBoundingClientRect();
    setProblem(null);
    setDrag({
      block,
      pointerId: event.pointerId,
      x0: event.clientX,
      y0: event.clientY,
      grab: (event.clientY - rect.top) / PX_PER_MINUTE,
      date: start.date,
      minutes: start.minutes,
      moved: false,
    });
  }

  /** Past the threshold (or already dragging), the drag at this event's position. */
  function dragAt(event: ReactPointerEvent, current: Drag): Drag | null {
    const far =
      Math.abs(event.clientX - current.x0) > DRAG_THRESHOLD_PX ||
      Math.abs(event.clientY - current.y0) > DRAG_THRESHOLD_PX;
    if (!current.moved && !far) return null;
    return { ...current, ...target(event, current), moved: true };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const current = dragRef.current;
    if (current === null || event.pointerId !== current.pointerId) return;
    const next = dragAt(event, current);
    if (next === null) return;
    // Capture only once it's a drag: a plain click must still reach the card's popover.
    if (!current.moved) event.currentTarget.setPointerCapture?.(event.pointerId);
    setDrag(next);
  }

  async function onPointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    const current = dragRef.current;
    if (current === null || event.pointerId !== current.pointerId) return;
    // The drop is where the pointer is released, not where the last render put the ghost.
    const done = dragAt(event, current);
    setDrag(null);
    if (done === null) return;
    justDragged.current = true;
    window.setTimeout(() => (justDragged.current = false), 0);
    const from = zoned(done.block.start, timeZone);
    if (from.date === done.date && from.minutes === done.minutes) return;
    setPlaced({ blockId: done.block.id, date: done.date, minutes: done.minutes });
    try {
      await move.mutateAsync({
        blockId: done.block.id,
        start: fromZoned(done.date, done.minutes, timeZone).toISOString(),
      });
    } catch (err) {
      setProblem({
        blockId: done.block.id,
        text: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setPlaced(null);
    }
  }

  const ghost: Placed | null = drag?.moved
    ? { blockId: drag.block.id, date: drag.date, minutes: drag.minutes }
    : placed;

  return (
    // overflow-clip, not hidden: a hidden overflow would be the sticky header's scroll box.
    <div className="surface-card overflow-clip rounded-xl" data-testid="week-grid">
      {/* The day headers stay under the floating nav while a long grid scrolls. */}
      <div
        data-testid="week-grid-header"
        className="border-line bg-surface sticky top-[4.5rem] z-20 grid grid-cols-[3.5rem_repeat(7,minmax(0,1fr))] rounded-t-xl border-b"
      >
        <div />
        {week.map((date) => {
          const off = unavailable.has(date);
          return (
            <div
              key={date}
              className={cn(
                "border-line flex min-w-0 items-start justify-between gap-1 border-l px-2 py-2",
                date === today && "bg-accent-soft",
              )}
            >
              <div className="min-w-0">
                <p className={cn("text-sm font-semibold", date === today && "text-link")}>
                  {dayLabel(date)}
                </p>
                {off && <p className="text-muted text-xs">Unavailable</p>}
              </div>
              {/* A past day can't be changed (decision 0023); today still can. */}
              {date >= today && (
                <DayMenu date={date} unavailable={off} exception={exceptions[date]} />
              )}
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-[3.5rem_repeat(7,minmax(0,1fr))] pt-3 pb-3">
        <div className="relative" style={{ height }} aria-hidden>
          {hours.map((hour) => (
            <span
              key={hour}
              className="text-muted absolute right-2 -translate-y-1/2 text-[11px] tabular-nums"
              style={{ top: (hour - range.first) * 60 * PX_PER_MINUTE }}
            >
              {clock(hour * 60)}
            </span>
          ))}
        </div>
        {week.map((date, index) => (
          <div
            key={date}
            ref={(el) => {
              columns.current[index] = el;
            }}
            data-date={date}
            className={cn("border-line relative border-l", date === today && "bg-accent-soft/40")}
            style={{ height }}
          >
            {hours.slice(1, -1).map((hour) => (
              <div
                key={hour}
                aria-hidden
                className="border-line absolute inset-x-0 border-t border-dashed"
                style={{ top: (hour - range.first) * 60 * PX_PER_MINUTE }}
              />
            ))}
            {(freeByDate[date] ?? []).map((span) => (
              <div
                key={`${span.start}-${span.end}`}
                aria-hidden
                data-free-band
                className="absolute inset-x-1 rounded-md bg-[color-mix(in_srgb,var(--accent-soft)_60%,transparent)]"
                style={{
                  top: (span.start - top) * PX_PER_MINUTE,
                  height: (span.end - span.start) * PX_PER_MINUTE,
                }}
              />
            ))}
            {placedBlocks
              .filter(({ start }) => start.date === date)
              .map(({ block, start }) => {
                const dragging = ghost?.blockId === block.id || drag?.block.id === block.id;
                const style = {
                  top: (start.minutes - top) * PX_PER_MINUTE,
                  height: block.minutes * PX_PER_MINUTE,
                };
                return (
                  <div
                    key={block.id}
                    className={cn(
                      "absolute inset-x-1 touch-none",
                      block.actions.move && "cursor-grab active:cursor-grabbing",
                      dragging && ghost && "opacity-40",
                    )}
                    style={style}
                    onPointerDown={(e) => onPointerDown(e, block)}
                    onPointerMove={onPointerMove}
                    onPointerUp={(e) => void onPointerUp(e)}
                    onPointerCancel={() => setDrag(null)}
                  >
                    <BlockPopover
                      block={block}
                      timeZone={timeZone}
                      week={week}
                      freeByDate={freeByDate}
                      open={openId === block.id}
                      onOpenChange={(open) => setOpenId(open ? block.id : null)}
                    >
                      <PlanBlockCard
                        block={block}
                        timeZone={timeZone}
                        now={now}
                        compact={block.minutes < 40}
                        startOnly
                        className="h-full"
                        onClick={(e) => {
                          if (justDragged.current) e.preventDefault();
                        }}
                      />
                    </BlockPopover>
                    {problem?.blockId === block.id && (
                      <p
                        role="alert"
                        className="glass-strong text-danger absolute top-full left-0 z-20 mt-1 w-56 rounded-md px-3 py-2 text-xs font-medium shadow-lg"
                      >
                        {problem.text}
                      </p>
                    )}
                  </div>
                );
              })}
            {ghost && ghost.date === date && (
              <GhostCard
                block={(drag?.block ?? blocks.find((b) => b.id === ghost.blockId))!}
                minutes={ghost.minutes}
                top={top}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function GhostCard({ block, minutes, top }: { block: PlanBlock; minutes: number; top: number }) {
  return (
    <div
      aria-hidden
      data-testid="drag-ghost"
      className="bg-surface border-ring pointer-events-none absolute inset-x-1 z-10 rounded-md border-2 border-l-4 px-2.5 py-1.5 shadow-lg"
      style={{
        top: (minutes - top) * PX_PER_MINUTE,
        height: block.minutes * PX_PER_MINUTE,
        borderLeftColor: block.module_colour,
      }}
    >
      <span className="text-xs font-semibold tabular-nums">
        {clock(minutes)}–{clock(minutes + block.minutes)}
      </span>
    </div>
  );
}
