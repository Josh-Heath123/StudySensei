import { useId, useState, type FormEvent } from "react";

import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";

import { usePracticeSettings, useUpdatePracticeSettings, type PracticeSettings } from "./api";

/** Settings → Practice (ADR 0026): new cards a day and the desired retention. */
export function PracticeSettingsCard() {
  const settings = usePracticeSettings();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Practice</CardTitle>
        <CardDescription>How many new cards a day, and how well to remember them.</CardDescription>
      </CardHeader>
      <CardContent>
        {settings.isError && (
          <p role="alert" className="text-danger text-sm">
            {settings.error.message}
          </p>
        )}
        {settings.isPending && <div aria-busy="true" className="skeleton h-32" />}
        {settings.data && <SettingsForm initial={settings.data} />}
      </CardContent>
    </Card>
  );
}

function SettingsForm({ initial }: { initial: PracticeSettings }) {
  const save = useUpdatePracticeSettings();
  const [perDay, setPerDay] = useState(String(initial.new_per_day));
  const [retention, setRetention] = useState(String(Math.round(initial.desired_retention * 100)));
  const [saved, setSaved] = useState(false);
  const id = useId();
  const perDayValue = Number(perDay);
  const retentionValue = Number(retention);
  const valid =
    Number.isInteger(perDayValue) &&
    perDayValue >= 0 &&
    perDayValue <= 200 &&
    retention.trim() !== "" &&
    retentionValue >= 80 &&
    retentionValue <= 97;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setSaved(false);
    try {
      await save.mutateAsync({
        new_per_day: perDayValue,
        desired_retention: Math.round(retentionValue) / 100,
      });
      setSaved(true);
    } catch {
      // Shown below.
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="grid gap-4">
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-new`}>New cards a day</Label>
        <Input
          id={`${id}-new`}
          type="number"
          inputMode="numeric"
          min={0}
          max={200}
          value={perDay}
          className="w-32"
          aria-describedby={`${id}-new-help`}
          onChange={(event) => setPerDay(event.target.value)}
        />
        <p id={`${id}-new-help`} className="text-muted text-xs">
          0 to 200. Cards you've never reviewed come in at most this many a day.
        </p>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${id}-retention`}>Desired retention (%)</Label>
        <Input
          id={`${id}-retention`}
          type="number"
          inputMode="numeric"
          min={80}
          max={97}
          value={retention}
          className="w-32"
          aria-describedby={`${id}-retention-help`}
          onChange={(event) => setRetention(event.target.value)}
        />
        <p id={`${id}-retention-help`} className="text-muted text-xs">
          Higher means more reviews and better recall. 80 to 97; it applies to reviews from now on.
        </p>
      </div>
      {save.isError && (
        <p role="alert" className="text-danger text-sm">
          {save.error.message}
        </p>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!valid || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <span aria-live="polite" className="text-success text-sm">
          {saved ? "Saved." : ""}
        </span>
      </div>
    </form>
  );
}
