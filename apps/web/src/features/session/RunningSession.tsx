import { ArrowLeft } from "lucide-react";
import type { CSSProperties } from "react";
import { Link } from "react-router";

import { formatDuration } from "@/session-engine/format";
import { DEFAULT_PLAN } from "@/session-engine/timer";
import { Button } from "@/ui/button";
import { ModuleBadge } from "@/ui/module-badge";
import { SegmentedProgress } from "@/ui/segmented-progress";

import { useModule, useTopicTree } from "../modules/api";
import type { SessionController, SessionMeta } from "./controller";
import { timerView } from "./display";
import { AwayDialog } from "./AwayDialog";
import { MaterialsCard, TutorPlaceholder } from "./SessionPanels";
import { SessionBanners } from "./SessionBanners";
import { findTopicName } from "./topics";
import { useDocumentTitle, useSessionClock } from "./useSessionClock";

const PLAN = DEFAULT_PLAN;

/**
 * The signature gradient's stops (docs/DESIGN.md "Colour": pink, lilac, violet). An SVG
 * stroke can't use the CSS `--gradient`, so this is the one place they're written out.
 */
const RING_STOPS = ["#FE6BD4", "#A77BF6", "#5840FF"] as const;
const RING_RADIUS = 47;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

/**
 * docs/DESIGN.md "Screens: Session": a clean header, the timer inside its gradient ring
 * over a faint mist, the floating glass control bar, then materials and the tutor.
 */
export function RunningSession({
  controller,
  meta,
}: {
  controller: SessionController;
  meta: SessionMeta;
}) {
  useSessionClock(controller);
  const module = useModule(meta.moduleId);
  const tree = useTopicTree(meta.moduleId);
  const snapshot = controller.snapshot();
  const view = snapshot === null ? null : timerView(snapshot, PLAN);
  useDocumentTitle(view?.title ?? "StudySensei");

  if (snapshot === null || view === null) {
    return <p className="text-muted p-10 text-sm">Loading…</p>;
  }

  const topicName = findTopicName(tree.data ?? [], meta.topicId);
  const away = snapshot.away;
  const blocked = away !== null;
  const can = (type: Parameters<SessionController["canRecord"]>[0]) =>
    !blocked && controller.canRecord(type);

  return (
    <div
      className="relative isolate min-h-screen overflow-x-clip"
      style={{ "--module": module.data?.colour } as CSSProperties}
    >
      <header className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-5 gap-y-3 px-4 py-5 sm:px-8 lg:px-10">
        <Link
          to="/"
          className="text-muted hover:text-fg hover:bg-subtle -ml-2 inline-flex min-h-9 items-center gap-1 rounded-md px-2 text-sm font-semibold"
        >
          <ArrowLeft className="size-4" aria-hidden /> Today
        </Link>
        {module.data && <ModuleBadge>{module.data.code}</ModuleBadge>}
        <h1 className="type-h3 min-w-0 flex-1 break-words">{topicName ?? "Whole module"}</h1>
      </header>

      <main className="mx-auto grid max-w-[1440px] items-start gap-8 px-4 pt-2 pb-12 sm:px-8 lg:grid-cols-[3fr_2fr] lg:px-10">
        <div className="grid min-w-0 gap-8">
          <SessionBanners controller={controller} snapshot={snapshot} plan={PLAN} />
          <section aria-label="Timer" className="grid justify-items-center gap-6">
            <div className="relative grid aspect-square w-full max-w-[560px] place-items-center">
              {/* The ambient mist: two soft, blurred glows behind the ring. */}
              <div aria-hidden className="pointer-events-none absolute -inset-[15%] -z-10">
                <div className="absolute top-0 left-0 size-[72%] rounded-full bg-[radial-gradient(closest-side,var(--mist-a),transparent)] blur-3xl" />
                <div className="absolute right-0 bottom-0 size-[78%] rounded-full bg-[radial-gradient(closest-side,var(--mist-b),transparent)] blur-3xl" />
              </div>
              <div
                role="progressbar"
                aria-label={
                  view.eyebrow.startsWith("Break") ? "Break so far" : "Focus block so far"
                }
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(view.progress * 100)}
                className="absolute inset-0"
              >
                <ProgressRing progress={view.progress} />
              </div>
              <div className="relative grid justify-items-center px-6 text-center">
                <p className="type-label text-muted mb-3">{view.eyebrow}</p>
                <p role="timer" className="type-timer max-sm:text-[72px]">
                  {view.numerals}
                </p>
              </div>
            </div>

            {/* The floating control bar: one primary action, the rest secondary. */}
            <div className="glass flex flex-wrap items-center justify-center gap-2 rounded-2xl p-2">
              {snapshot.state === "active" && (
                <>
                  <Button disabled={!can("pause")} onClick={() => void controller.pause()}>
                    Pause
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!can("break_start")}
                    onClick={() => void controller.breakStart()}
                  >
                    Break now
                  </Button>
                </>
              )}
              {snapshot.state === "paused" && (
                <Button disabled={!can("resume")} onClick={() => void controller.resume()}>
                  Resume
                </Button>
              )}
              {snapshot.state === "on_break" && (
                <Button disabled={!can("break_end")} onClick={() => void controller.breakEnd()}>
                  End break
                </Button>
              )}
              <Button
                variant="outline"
                disabled={!can("end")}
                onClick={() => void controller.end()}
              >
                End session
              </Button>
            </div>

            <div className="surface-card grid w-full gap-4 rounded-xl p-5 sm:p-6">
              <SegmentedProgress segments={view.segments} />
              <p className="text-muted text-sm">
                <span className="tabular">
                  Active {formatDuration(snapshot.totals.activeMs)} · Break{" "}
                  {formatDuration(snapshot.totals.breakMs)}
                </span>{" "}
                <span className="text-xs">
                  (Measured · from {snapshot.eventCount} timer{" "}
                  {snapshot.eventCount === 1 ? "event" : "events"})
                </span>
              </p>
            </div>
          </section>
          <MaterialsCard moduleId={meta.moduleId} />
        </div>
        <TutorPlaceholder />
      </main>

      {away && <AwayDialog message={away.message} controller={controller} />}
    </div>
  );
}

/** The block so far as a gradient arc on a soft violet track. Decorative: the parent is the progressbar. */
function ProgressRing({ progress }: { progress: number }) {
  const done = Math.min(Math.max(progress, 0), 1);
  return (
    // Rotated so the arc starts at twelve o'clock (a fixed angle, not motion).
    <svg viewBox="0 0 100 100" aria-hidden className="size-full -rotate-90">
      <defs>
        <linearGradient id="session-ring-gradient" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor={RING_STOPS[0]} />
          <stop offset="50%" stopColor={RING_STOPS[1]} />
          <stop offset="100%" stopColor={RING_STOPS[2]} />
        </linearGradient>
      </defs>
      <circle
        cx="50"
        cy="50"
        r={RING_RADIUS}
        fill="none"
        strokeWidth="1.25"
        className="stroke-accent-soft"
      />
      <circle
        cx="50"
        cy="50"
        r={RING_RADIUS}
        fill="none"
        stroke="url(#session-ring-gradient)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={RING_CIRCUMFERENCE}
        strokeDashoffset={RING_CIRCUMFERENCE * (1 - done)}
        // A round cap would show a dot at 0%.
        opacity={done === 0 ? 0 : 1}
        className="ease-soft transition-[stroke-dashoffset] duration-200"
      />
    </svg>
  );
}
