import { Plus, X } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";

import { useCreateException, useDeleteException, useExceptions } from "./api";
import { type Clock, fromInput, nextWindow, shortDate } from "./studyTime";

/** Dates that don't follow the week: unavailable all day, or different times. */
export function ExceptionsCard({ today }: { today: string }) {
  const exceptions = useExceptions(today);
  const remove = useDeleteException();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Exceptions</CardTitle>
        <CardDescription>
          A date that's different: a day off, a test, or other times than usual.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {exceptions.data && exceptions.data.length > 0 && (
          <ul aria-label="Exceptions" className="divide-line divide-y">
            {exceptions.data.map((exception) => {
              const when = shortDate(exception.date);
              return (
                <li key={exception.id} className="flex items-start gap-2 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{when}</p>
                    <p className="text-muted text-sm">
                      {exception.unavailable
                        ? "Unavailable all day"
                        : exception.windows.map((w) => `${w.start}–${w.end}`).join(", ")}
                      {exception.note && ` · ${exception.note}`}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove the exception on ${when}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(exception.id)}
                  >
                    <X aria-hidden />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        {exceptions.data?.length === 0 && (
          <p className="text-muted text-sm">No exceptions coming up.</p>
        )}
        {remove.isError && (
          <p role="alert" className="text-danger text-sm">
            {remove.error.message}
          </p>
        )}
        <AddException today={today} />
      </CardContent>
    </Card>
  );
}

function AddException({ today }: { today: string }) {
  const create = useCreateException();
  const name = useId();
  const [date, setDate] = useState("");
  const [unavailable, setUnavailable] = useState(true);
  const [windows, setWindows] = useState<Clock[]>([{ start: "18:00", end: "19:00" }]);
  const [note, setNote] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!date) return;
    try {
      await create.mutateAsync({
        date,
        unavailable,
        windows: unavailable
          ? []
          : windows.map((w) => ({ start: w.start, end: fromInput(w.end, true) })),
        note: note.trim() || null,
      });
      setDate("");
      setNote("");
    } catch {
      // Shown below; the form keeps what was typed.
    }
  }

  function setWindow(index: number, change: Partial<Clock>) {
    setWindows((now) => now.map((w, i) => (i === index ? { ...w, ...change } : w)));
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Add an exception"
      className="border-line grid gap-3 border-t pt-4"
    >
      <div className="grid gap-2">
        <Label htmlFor={`${name}-date`}>Date</Label>
        <Input
          id={`${name}-date`}
          type="date"
          min={today}
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="w-44"
        />
      </div>
      <fieldset className="grid gap-2">
        <legend className="sr-only">That day</legend>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name={`${name}-kind`}
            checked={unavailable}
            onChange={() => setUnavailable(true)}
            className="accent-primary size-4"
          />
          Unavailable all day
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name={`${name}-kind`}
            checked={!unavailable}
            onChange={() => setUnavailable(false)}
            className="accent-primary size-4"
          />
          Different times
        </label>
      </fieldset>
      {!unavailable && (
        <div className="grid gap-2">
          {windows.map((window, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2">
              <Input
                type="time"
                aria-label={`Exception window ${index + 1} start`}
                value={window.start}
                onChange={(event) => setWindow(index, { start: event.target.value })}
                className="w-32"
              />
              <span aria-hidden className="text-muted">
                to
              </span>
              <Input
                type="time"
                aria-label={`Exception window ${index + 1} end`}
                value={window.end}
                onChange={(event) => setWindow(index, { end: event.target.value })}
                className="w-32"
              />
              {windows.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove exception window ${index + 1}`}
                  onClick={() => setWindows((now) => now.filter((_, i) => i !== index))}
                >
                  <X aria-hidden />
                </Button>
              )}
            </div>
          ))}
          <div>
            <Button
              type="button"
              variant="quiet"
              size="sm"
              disabled={nextWindow(windows) === null}
              onClick={() => {
                const next = nextWindow(windows);
                if (next) setWindows((now) => [...now, next]);
              }}
            >
              <Plus aria-hidden />
              Another window
            </Button>
          </div>
        </div>
      )}
      <div className="grid gap-2">
        <Label htmlFor={`${name}-note`}>Note (optional)</Label>
        <Input
          id={`${name}-note`}
          value={note}
          maxLength={200}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Graduation, a test…"
        />
      </div>
      {create.isError && (
        <p role="alert" className="text-danger text-sm">
          {create.error.message}
        </p>
      )}
      <div>
        <Button type="submit" variant="outline" disabled={!date || create.isPending}>
          Add exception
        </Button>
      </div>
    </form>
  );
}
