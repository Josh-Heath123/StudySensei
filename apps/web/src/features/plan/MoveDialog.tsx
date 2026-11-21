import { useMemo, useState, type FormEvent } from "react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";

import { useMoveBlock, type PlanBlock } from "./api";
import { blockName } from "./planText";
import { clock, dayLabel, fromZoned, startsWithin, zoned, type Span } from "./week";

type Props = {
  block: PlanBlock;
  timeZone: string;
  week: string[];
  freeByDate: Record<string, Span[]>;
  onClose: (moved: boolean) => void;
};

/**
 * Move… (the keyboard path for dragging): a day of the week and a 5-minute time inside that
 * day's free windows. The server checks the move; its one-sentence reason shows here.
 */
export function MoveDialog({ block, timeZone, week, freeByDate, onClose }: Props) {
  const move = useMoveBlock();
  const length = block.minutes;
  const current = zoned(block.start, timeZone);
  const days = week.filter((date) => startsWithin(freeByDate[date] ?? [], length).length > 0);
  const [day, setDay] = useState(days.includes(current.date) ? current.date : (days[0] ?? ""));
  const times = useMemo(
    () => startsWithin(freeByDate[day] ?? [], length),
    [freeByDate, day, length],
  );
  // It opens on the block's own day and time (decision 0023), not that day's first free time.
  const [time, setTime] = useState<number | null>(
    days.includes(current.date) ? current.minutes : null,
  );
  const chosen = time !== null && times.includes(time) ? time : (times[0] ?? null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen === null || !day) return;
    setError(null);
    try {
      await move.mutateAsync({
        blockId: block.id,
        start: fromZoned(day, chosen, timeZone).toISOString(),
      });
      onClose(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move {blockName(block)}</DialogTitle>
          <DialogDescription>
            Now {dayLabel(current.date)} at {clock(current.minutes)}. It keeps its {length} min.
          </DialogDescription>
        </DialogHeader>
        {days.length === 0 ? (
          <p className="text-muted text-sm">No free window this week is long enough.</p>
        ) : (
          <form id="move-block" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="move-day">Day</Label>
              <NativeSelect
                id="move-day"
                value={day}
                onChange={(e) => {
                  setDay(e.target.value);
                  setTime(null);
                }}
              >
                {days.map((date) => (
                  <option key={date} value={date}>
                    {dayLabel(date)}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="move-time">Start</Label>
              <NativeSelect
                id="move-time"
                value={chosen ?? ""}
                onChange={(e) => setTime(Number(e.target.value))}
              >
                {times.map((t) => (
                  <option key={t} value={t}>
                    {clock(t)}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </form>
        )}
        {error && (
          <p role="alert" className="text-danger text-sm">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} disabled={move.isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="move-block"
            disabled={move.isPending || chosen === null || days.length === 0}
          >
            {move.isPending ? "Moving…" : "Move"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
