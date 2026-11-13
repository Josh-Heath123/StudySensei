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

/** docs/DESIGN.md "Study session": header, progress line, timer, materials, tutor. */
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

  if (snapshot === null || view === null) return <p className="text-muted text-sm">Loading…</p>;

  const topicName = findTopicName(tree.data ?? [], meta.topicId);
  const away = snapshot.away;
  const blocked = away !== null;
  const can = (type: Parameters<SessionController["canRecord"]>[0]) =>
    !blocked && controller.canRecord(type);

  return (
    <div style={{ "--module": module.data?.colour } as CSSProperties}>
      <header className="border-ink border-b-2">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4 sm:px-10">
          <Link
            to="/"
            className="text-muted hover:text-ink inline-flex items-center gap-1 text-sm font-semibold"
          >
            <ArrowLeft className="size-4" aria-hidden /> Today
          </Link>
          {module.data && <ModuleBadge>{module.data.code}</ModuleBadge>}
          <h1 className="type-h3 min-w-0 flex-1 break-words">{topicName ?? "Whole module"}</h1>
          <Button disabled={!can("end")} onClick={() => void controller.end()}>
            End session
          </Button>
        </div>
      </header>
      <div
        role="progressbar"
        aria-label={view.eyebrow.startsWith("Break") ? "Break so far" : "Focus block so far"}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(view.progress * 100)}
        className="bg-surface h-1.5"
      >
        <div
          className="h-full bg-[var(--module)] transition-[width] duration-150 ease-out"
          style={{ width: `${view.progress * 100}%` }}
        />
      </div>

      <main className="mx-auto grid max-w-[1440px] items-start gap-8 px-5 py-8 sm:px-10 sm:py-10 lg:grid-cols-[3fr_2fr]">
        <div className="grid min-w-0 gap-8">
          <SessionBanners controller={controller} snapshot={snapshot} plan={PLAN} />
          <section aria-label="Timer" className="grid gap-6">
            <div>
              <p className="type-label text-muted mb-3">{view.eyebrow}</p>
              <p role="timer" className="type-timer max-sm:text-[72px]">
                {view.numerals}
              </p>
            </div>
            <SegmentedProgress segments={view.segments} />
            <div className="flex flex-wrap gap-3">
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
            </div>
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
          </section>
          <MaterialsCard moduleId={meta.moduleId} />
        </div>
        <TutorPlaceholder />
      </main>

      {away && <AwayDialog message={away.message} controller={controller} />}
    </div>
  );
}
