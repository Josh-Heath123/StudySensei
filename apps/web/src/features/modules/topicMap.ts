import type { TopicMapStatus } from "./api";

export type TopicMapView = {
  /** What to tell the student, in one or two plain sentences. */
  message: string;
  /** Extra detail, e.g. why some materials couldn't be analysed. */
  detail?: string;
  /** Analysed so far, while materials are being analysed. */
  progress?: { done: number; total: number };
  canBuild: boolean;
  busy: boolean;
};

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

/**
 * The topic map panel's state, honestly: no AI key, nothing to analyse, AI resting,
 * analysing (with progress), merging, or ready to build. `aiAvailable` is undefined
 * while /ai/status loads.
 */
export function describeTopicMap(
  status: TopicMapStatus,
  aiAvailable: boolean | undefined,
  now: Date = new Date(),
): TopicMapView {
  const { eligible, analysed, pending, failed, merging } = status;
  const failures =
    failed > 0
      ? `${plural(failed, "material")} couldn't be analysed${status.last_error ? `: ${status.last_error}` : "."}`
      : undefined;

  if (aiAvailable === false) {
    return {
      message:
        "AI isn't set up, so topic maps can't be built. Add GEMINI_API_KEY or GROQ_API_KEY to apps/api/.env and restart the API and worker.",
      canBuild: false,
      busy: false,
    };
  }
  if (eligible === 0) {
    return {
      message:
        "Nothing to analyse yet. Upload slides, notes, a study guide, a tutorial or an outline (with AI allowed) to build a topic map.",
      canBuild: false,
      busy: false,
    };
  }

  const waiting = status.waiting_until ? new Date(status.waiting_until) : null;
  if (waiting && waiting > now && (pending > 0 || merging)) {
    return {
      message: `The AI is resting until ${time(status.waiting_until!)} (free-tier limits). Analysed ${analysed} of ${plural(eligible, "material")} so far.`,
      detail: failures,
      progress: { done: analysed, total: eligible },
      canBuild: false,
      busy: true,
    };
  }
  if (pending > 0) {
    return {
      message: `Analysed ${analysed} of ${plural(eligible, "material")}…`,
      detail: failures,
      progress: { done: analysed, total: eligible },
      canBuild: false,
      busy: true,
    };
  }
  if (merging) {
    return {
      message: `Building the topic map from ${plural(analysed, "analysed material")}…`,
      detail: failures,
      canBuild: false,
      busy: true,
    };
  }

  const built = status.merged_at
    ? `Last built ${new Date(status.merged_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}. `
    : "";
  const remaining = eligible - analysed;
  return {
    message:
      remaining > 0
        ? `${built}${plural(remaining, "material")} not analysed yet (${analysed} of ${eligible} done).`
        : `${built}All ${plural(eligible, "material")} analysed. Building again adds only new topics.`,
    detail: failures,
    canBuild: true,
    busy: false,
  };
}
