import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";

import {
  type PlanningSettings,
  type Rule,
  useAvailability,
  useCreateRule,
  useDeleteRule,
  usePlanningSettings,
  useRules,
  useUpdatePlanningSettings,
  useUpdateRule,
} from "./api";
import { ExceptionsCard } from "./ExceptionsCard";
import {
  addDays,
  type Clock,
  deviceTimezone,
  fromInput,
  hoursText,
  localToday,
  nextWindow,
  timezoneOptions,
  toInput,
  WEEKDAYS,
  windowLength,
} from "./studyTime";

/**
 * Settings → Study time: when the student can study each week, the most a day, their
 * timezone, and dates that don't follow the week. The planner (Phase 4) uses only this time.
 */
export function StudyTimeSection() {
  const settings = usePlanningSettings();
  const rules = useRules();
  const today = settings.data ? localToday(settings.data.timezone) : null;

  return (
    <section aria-labelledby="study-time" className="mt-12 grid gap-6">
      <div>
        <h2 id="study-time" className="type-h2">
          Study time
        </h2>
        <p className="text-muted mt-2 max-w-2xl">
          When you can study, so the plan only uses that time. Times are in your timezone.
        </p>
      </div>
      {(settings.isError || rules.isError) && (
        <p role="alert" className="text-danger">
          {(settings.error ?? rules.error)?.message}
        </p>
      )}
      {settings.data && rules.data && today && (
        <>
          <WeekSummary today={today} hasRules={rules.data.length > 0} />
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <WeeklyCard rules={rules.data} />
            <div className="grid min-w-0 gap-6">
              <LimitsCard settings={settings.data} />
              <ExceptionsCard today={today} />
            </div>
          </div>
        </>
      )}
      {(settings.isPending || rules.isPending) && (
        <div aria-busy="true" className="surface-card grid gap-3 rounded-xl p-5">
          <p className="sr-only">Loading your study time…</p>
          <div aria-hidden className="skeleton h-5 w-1/3" />
          <div aria-hidden className="skeleton h-9 w-full" />
        </div>
      )}
    </section>
  );
}

/** "≈ 12 h a week available (from your rules)", and the next 7 days with exceptions. */
function WeekSummary({ today, hasRules }: { today: string; hasRules: boolean }) {
  const week = useAvailability(today, addDays(today, 6));
  if (!week.data) return <p className="text-muted">Working out your week…</p>;
  if (!hasRules) {
    return (
      <p role="status" className="text-muted">
        No study time yet: add a window to a day below.
      </p>
    );
  }
  return (
    <p role="status" className="text-base">
      <span className="font-semibold">
        ≈ {hoursText(week.data.weekly_minutes_from_rules)} a week available
      </span>{" "}
      <span className="text-muted">(from your rules)</span>
      <span className="text-muted"> · </span>
      <span>≈ {hoursText(week.data.total_available_minutes)} in the next 7 days</span>{" "}
      <span className="text-muted">(with your exceptions, at most the daily cap a day)</span>
    </p>
  );
}

function WeeklyCard({ rules }: { rules: Rule[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Each week</CardTitle>
        <CardDescription>
          Add the times you can study on each day. A window ends by midnight: split a late one
          across two days.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul aria-label="Weekly study times" className="divide-line divide-y">
          {WEEKDAYS.map((day, weekday) => (
            <DayRow
              key={day}
              day={day}
              weekday={weekday}
              rules={rules.filter((rule) => rule.weekday === weekday)}
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function DayRow({ day, weekday, rules }: { day: string; weekday: number; rules: Rule[] }) {
  const create = useCreateRule();
  const update = useUpdateRule();
  const remove = useDeleteRule();
  const next = nextWindow(rules);
  const total = rules.reduce((sum, rule) => sum + windowLength(rule), 0);
  const error = create.error ?? update.error ?? remove.error;

  return (
    <li aria-label={day} className="grid gap-2 py-3 first:pt-0 last:pb-0 sm:grid-cols-[7rem_1fr]">
      <div className="flex items-baseline justify-between gap-2 sm:block">
        <p className="font-semibold">{day}</p>
        <p className="text-muted tabular text-xs">{total > 0 ? hoursText(total) : "Not set"}</p>
      </div>
      <div className="grid gap-2">
        {rules.map((rule, index) => (
          <WindowRow
            // Remount with the saved times after each change.
            key={`${rule.id}-${rule.start}-${rule.end}`}
            label={`${day} window ${index + 1}`}
            window={rule}
            onSave={(clock) => update.mutate({ id: rule.id, ...clock })}
            onRemove={() => remove.mutate(rule.id)}
          />
        ))}
        <div>
          <Button
            variant="quiet"
            size="sm"
            disabled={next === null || create.isPending}
            onClick={() => {
              update.reset();
              remove.reset();
              if (next) create.mutate({ weekday, ...next });
            }}
            aria-label={`Add a window on ${day}`}
          >
            <Plus aria-hidden />
            Add a window
          </Button>
        </div>
        {error && (
          <p role="alert" className="text-danger text-sm">
            {error.message}
          </p>
        )}
      </div>
    </li>
  );
}

/** One window: two time inputs, saved when either loses focus with a change. */
function WindowRow({
  label,
  window,
  onSave,
  onRemove,
}: {
  label: string;
  window: Clock;
  onSave: (clock: Clock) => void;
  onRemove: () => void;
}) {
  const [start, setStart] = useState(toInput(window.start));
  const [end, setEnd] = useState(toInput(window.end));

  function save() {
    const clock = { start: fromInput(start, false), end: fromInput(end, true) };
    if (!start || !end) return;
    if (clock.start !== window.start || clock.end !== window.end) onSave(clock);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        type="time"
        aria-label={`${label} start`}
        value={start}
        onChange={(event) => setStart(event.target.value)}
        onBlur={save}
        className="w-32"
      />
      <span aria-hidden className="text-muted">
        to
      </span>
      <Input
        type="time"
        aria-label={`${label} end`}
        value={end}
        onChange={(event) => setEnd(event.target.value)}
        onBlur={save}
        className="w-32"
      />
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`Remove ${label} (${window.start} to ${window.end})`}
        onClick={onRemove}
      >
        <X aria-hidden />
      </Button>
    </div>
  );
}

function LimitsCard({ settings }: { settings: PlanningSettings }) {
  const update = useUpdatePlanningSettings();
  const [cap, setCap] = useState(String(settings.daily_study_cap_minutes));
  const minutes = Number(cap);
  const valid = Number.isInteger(minutes) && minutes >= 15 && minutes <= 1440;
  const device = deviceTimezone();

  function saveCap() {
    if (valid && minutes !== settings.daily_study_cap_minutes) {
      update.mutate({ daily_study_cap_minutes: minutes });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Limits</CardTitle>
        <CardDescription>The most the plan puts in one day, and your timezone.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-2">
          <Label htmlFor="daily-cap">Most study a day (minutes)</Label>
          <div className="flex items-center gap-3">
            <Input
              id="daily-cap"
              type="number"
              inputMode="numeric"
              min={15}
              max={1440}
              step={15}
              value={cap}
              aria-invalid={!valid}
              onChange={(event) => setCap(event.target.value)}
              onBlur={saveCap}
              onKeyDown={(event) => event.key === "Enter" && saveCap()}
              className="w-28"
            />
            <span className="text-muted text-sm">
              {valid ? `= ${hoursText(minutes)}` : "15 to 1,440 minutes"}
            </span>
          </div>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="timezone">Timezone</Label>
          <NativeSelect
            id="timezone"
            value={settings.timezone}
            onChange={(event) => update.mutate({ timezone: event.target.value })}
          >
            {timezoneOptions(settings.timezone).map((zone) => (
              <option key={zone} value={zone}>
                {zone.replaceAll("_", " ")}
              </option>
            ))}
          </NativeSelect>
          {device && device !== settings.timezone && (
            <p className="text-muted text-xs">
              This device is on {device.replaceAll("_", " ")}.{" "}
              <button
                type="button"
                className="text-link cursor-pointer font-semibold"
                onClick={() => update.mutate({ timezone: device })}
              >
                Use it
              </button>
            </p>
          )}
        </div>
        {update.isError && (
          <p role="alert" className="text-danger text-sm">
            {update.error.message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
