import { CalendarClock, ChevronLeft, ChevronRight, GraduationCap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { EmptyState } from "@/features/modules/EmptyState";
import {
  useAvailability,
  useExceptions,
  usePlanningSettings,
  useRules,
} from "@/features/settings/api";
import { useMediaQuery, DESKTOP } from "@/lib/useMediaQuery";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

import { Agenda } from "./Agenda";
import { usePlan, type Plan } from "./api";
import { addDays, clock, dayLabel, mondayOf, toSpans, weekDates, zoned, type Span } from "./week";
import { WeekGrid } from "./WeekGrid";

const POLL_MS = 2000;
const POLL_FOR_MS = 30_000;

const STATUS_CHIP: Record<
  Plan["report"]["overall"]["status"],
  { label: string; className: string }
> = {
  fits: { label: "Fits", className: "text-success border-success/40" },
  tight: { label: "Tight", className: "text-warning border-warning/40" },
  short: { label: "Short", className: "text-danger border-danger/40" },
};

/**
 * docs/DESIGN.md "Screens: Plan": the stored plan for a week (GET /plan). The header carries
 * the version's summary, the overall feasibility line with its status and the levers, with
 * the per-assessment lines under Details; then the week grid from 1024 px, or an agenda
 * below it. Every rule (what can move, be skipped or started) comes from the server.
 */
export function PlanPage() {
  const settings = usePlanningSettings();
  const timeZone = settings.data?.timezone ?? null;
  const nowDate = useNow(30_000);
  const now = nowDate.getTime();
  const today = timeZone ? zoned(now, timeZone).date : null;
  const [monday, setMonday] = useState<string | null>(null);
  const thisMonday = today ? mondayOf(today) : null;
  const shownMonday = monday ?? thisMonday;
  const week = useMemo(() => (shownMonday ? weekDates(shownMonday) : []), [shownMonday]);
  const sunday = week[6] ?? null;

  // Poll every 2 s while a re-plan is pending, for at most 30 s from when it was first seen.
  const pendingSince = useRef<number | null>(null);
  const plan = usePlan(shownMonday, sunday, (data) => {
    if (!data?.replan_pending) {
      pendingSince.current = null;
      return false;
    }
    pendingSince.current ??= Date.now();
    return Date.now() - pendingSince.current < POLL_FOR_MS ? POLL_MS : false;
  });
  const pending = plan.data?.replan_pending ?? false;
  const [gaveUp, setGaveUp] = useState(false);
  const [wasPending, setWasPending] = useState(pending);
  if (pending !== wasPending) {
    setWasPending(pending);
    if (!pending) setGaveUp(false);
  }
  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(() => setGaveUp(true), POLL_FOR_MS);
    return () => window.clearTimeout(timer);
  }, [pending]);

  const availability = useAvailability(shownMonday, sunday);
  const exceptions = useExceptions(shownMonday);
  const rules = useRules();
  const desktop = useMediaQuery(DESKTOP, true);

  const freeByDate = useMemo(() => {
    const out: Record<string, Span[]> = {};
    if (!timeZone) return out;
    for (const day of availability.data?.days ?? []) {
      out[day.date] = day.intervals.flatMap((i) => toSpans(i.start, i.end, timeZone));
    }
    return out;
  }, [availability.data, timeZone]);
  const unavailable = useMemo(
    () =>
      new Set(
        (availability.data?.days ?? [])
          .filter((d) => d.source === "unavailable")
          .map((d) => d.date),
      ),
    [availability.data],
  );
  const exceptionsByDate = useMemo(
    () => Object.fromEntries((exceptions.data ?? []).map((e) => [e.date, e])),
    [exceptions.data],
  );

  const data = plan.data;
  const header = (
    <PageHeader
      title="Plan"
      eyebrow={week.length ? `${dayLabel(week[0]!)} – ${dayLabel(week[6]!)}` : undefined}
      description={
        data && timeZone ? <VersionLine plan={data} timeZone={timeZone} now={now} /> : undefined
      }
      aside={
        <nav aria-label="Week" className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-label="Previous week"
            disabled={!shownMonday}
            onClick={() => setMonday(addDays(shownMonday!, -7))}
          >
            <ChevronLeft aria-hidden />
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!thisMonday || shownMonday === thisMonday}
            onClick={() => setMonday(null)}
          >
            This week
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label="Next week"
            disabled={!shownMonday}
            onClick={() => setMonday(addDays(shownMonday!, 7))}
          >
            <ChevronRight aria-hidden />
          </Button>
        </nav>
      }
    />
  );

  if (plan.isError) {
    return (
      <>
        {header}
        <p role="alert" className="text-danger">
          {plan.error.message}
        </p>
      </>
    );
  }
  if (!data || !timeZone || !today) {
    return (
      <>
        {header}
        <div className="skeleton h-96 rounded-xl" aria-label="Loading your plan" />
      </>
    );
  }

  const noStudyTime = (rules.data?.length ?? 1) === 0;
  const noAssessments = data.report.assessments.length === 0 && data.report.later.length === 0;
  const report = data.report;
  const chip = STATUS_CHIP[report.overall.status];

  return (
    <>
      {header}
      <div className="grid gap-6">
        {noStudyTime ? (
          <EmptyState
            icon={CalendarClock}
            title="Add your study time"
            action={
              <Button asChild>
                <Link to="/settings">Settings → Study time</Link>
              </Button>
            }
          >
            The plan fits blocks into the hours you can study.
          </EmptyState>
        ) : noAssessments ? (
          <EmptyState
            icon={GraduationCap}
            title="Nothing to plan for yet"
            action={
              <Button asChild>
                <Link to="/modules">Go to Modules</Link>
              </Button>
            }
          >
            Add an assessment with a date and its topics, and the plan fills in.
          </EmptyState>
        ) : (
          <section aria-label="Feasibility" className="surface-card grid gap-3 rounded-xl p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={cn(
                  "bg-surface rounded-sm border px-2 py-0.5 text-xs font-semibold",
                  chip.className,
                )}
              >
                {chip.label}
              </span>
              <p className="font-medium">{report.overall.line}</p>
            </div>
            {report.levers.length > 0 && (
              <ul className="text-muted grid gap-1 text-sm">
                {report.levers.map((lever) => (
                  <li key={`${lever.kind}-${lever.assessment_id ?? ""}`}>{lever.text}</li>
                ))}
              </ul>
            )}
            <details className="text-sm">
              <summary className="text-link cursor-pointer font-medium">Details</summary>
              <ul className="mt-2 grid gap-2">
                {report.assessments.map((a) => (
                  <li key={a.assessment_id}>
                    <p>{a.line}</p>
                    {a.issues.map((issue) => (
                      <p key={`${issue.kind}-${issue.topic_id ?? ""}`} className="text-muted">
                        {issue.text}
                      </p>
                    ))}
                  </li>
                ))}
                {report.later.map((later) => (
                  <li key={later.assessment_id} className="text-muted">
                    {later.text}
                  </li>
                ))}
              </ul>
              <p className="text-muted mt-2 text-xs">{report.basis}</p>
            </details>
          </section>
        )}

        {pending && (
          <p role="status" className="text-muted text-sm">
            {gaveUp ? "Still updating: refresh in a moment." : "Updating your plan…"}
          </p>
        )}

        {desktop ? (
          <WeekGrid
            blocks={data.blocks}
            week={week}
            today={today}
            timeZone={timeZone}
            now={now}
            freeByDate={freeByDate}
            unavailable={unavailable}
            exceptions={exceptionsByDate}
          />
        ) : (
          <Agenda
            blocks={data.blocks}
            week={week}
            today={today}
            timeZone={timeZone}
            now={now}
            freeByDate={freeByDate}
            unavailable={unavailable}
            exceptions={exceptionsByDate}
          />
        )}
      </div>
    </>
  );
}

/** "Updated 14:43 · You skipped …" (or "Updated Tue 24 Nov, 14:43 · …" on another day). */
function VersionLine({ plan, timeZone, now }: { plan: Plan; timeZone: string; now: number }) {
  const at = zoned(plan.generated_at, timeZone);
  const today = zoned(now, timeZone).date;
  const when = at.date === today ? clock(at.minutes) : `${dayLabel(at.date)}, ${clock(at.minutes)}`;
  return (
    <span className="text-muted">
      Updated {when} · {plan.summary}
    </span>
  );
}
