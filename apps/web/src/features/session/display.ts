/**
 * What the session screen draws, as a pure function of the engine's snapshot.
 * Nothing here reads the clock: the snapshot already holds every number.
 */
import type { Snapshot } from "@/session-engine/engine";
import type { CyclePlan } from "@/session-engine/timer";

export type Segment = {
  kind: "focus" | "break";
  label: string;
  minutes: number;
  /** How much of the segment has passed, 0–1. */
  filled: number;
};

export type TimerView = {
  /** The label above the numerals (sentence case; the screen shows it in capitals). */
  eyebrow: string;
  numerals: string;
  /** The 6 px line under the header: how far through the current block or break. */
  progress: number;
  /** The current cycle: one focus block, then one break. */
  segments: Segment[];
  /** For document.title, so the time shows from other tabs. */
  title: string;
};

const APP = "StudySensei";

/** "mm:ss", or "h:mm:ss" from an hour up. Partial seconds are dropped. */
export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** A countdown shows the whole second it's in: 49:59.6 left reads 50:00. */
const countdown = (ms: number) => formatClock(Math.ceil(ms / 1000) * 1000);

const ratio = (part: number, whole: number) => (whole > 0 ? Math.min(1, part / whole) : 1);

function segments(plan: CyclePlan, focusFilled: number, breakFilled: number): Segment[] {
  return [
    {
      kind: "focus",
      label: `Focus ${plan.focusMin} min`,
      minutes: plan.focusMin,
      filled: focusFilled,
    },
    {
      kind: "break",
      label: `Break ${plan.breakMin} min`,
      minutes: plan.breakMin,
      filled: breakFilled,
    },
  ];
}

export function timerView({ state, cycle, totals }: Snapshot, plan: CyclePlan): TimerView {
  if (cycle.phase === "ended") {
    return {
      eyebrow: "Ended",
      numerals: formatClock(totals.activeMs),
      progress: 1,
      segments: segments(plan, 1, 1),
      title: `Session ended · ${APP}`,
    };
  }

  if (cycle.phase === "break") {
    const target = plan.breakMin * 60_000;
    const progress = ratio(cycle.breakElapsedMs, target);
    const over = cycle.breakOverByMs > 0;
    const numerals = over
      ? `+${formatClock(cycle.breakOverByMs)}`
      : countdown(cycle.breakRemainingMs);
    return {
      eyebrow: over ? "Break · over time" : "Break",
      numerals,
      progress,
      segments: segments(plan, 1, progress),
      title: over ? `Break over · ${APP}` : `${numerals} break · ${APP}`,
    };
  }

  const target = plan.focusMin * 60_000;
  const progress = ratio(cycle.focusMs, target);
  const numerals = cycle.breakDue
    ? `+${formatClock(cycle.focusMs - target)}`
    : countdown(cycle.breakDueInMs);
  const view = { numerals, progress, segments: segments(plan, progress, 0) };
  if (state === "paused") {
    return { ...view, eyebrow: "Paused", title: `Paused · ${numerals} · ${APP}` };
  }
  return cycle.breakDue
    ? { ...view, eyebrow: "Focus · break due", title: `Break due · ${APP}` }
    : { ...view, eyebrow: "Focus", title: `${numerals} focus · ${APP}` };
}
