import type { PlanBlock } from "./api";
import { clock, dayLabel, zoned } from "./week";

/** The method as a short label for a card. */
export const METHOD_LABELS: Record<PlanBlock["method"], string> = {
  mixed_review: "Mixed review",
  first_pass: "First pass",
  active_recall: "Recall",
  practice: "Practice",
};

/** "Ch2 Cryptography", or "Final review · COS330 Exam" for a review. */
export function blockTitle(block: PlanBlock): string {
  return block.topic_name ?? `Final review · ${block.module_code} ${block.assessment_title}`;
}

/** For sentences: "Ch2 Cryptography", or "Final review for COS330 Exam". */
export function blockName(block: PlanBlock): string {
  return block.topic_name ?? `Final review for ${block.module_code} ${block.assessment_title}`;
}

/** "48 min (measured)" for a done block with a session. */
export function measuredText(block: PlanBlock): string | null {
  if (block.status !== "done" || block.session_minutes === null) return null;
  const minutes = block.session_minutes;
  return minutes < 1 ? "under 1 min (measured)" : `${minutes} min (measured)`;
}

/**
 * A card's accessible name: its day, title, time and state, so a screen reader can tell
 * cards apart in the grid. "Sat 21 Nov, Ch1 Overview, 09:00 to 09:50, first pass", or
 * "…, done, 48 min (measured)", "…, skipped", "…, missed", "…, now".
 */
export function blockLabel(block: PlanBlock, timeZone: string, now: number): string {
  const start = zoned(block.start, timeZone);
  const end = zoned(block.end, timeZone);
  const measured = measuredText(block);
  const state = isNow(block, now)
    ? "now"
    : block.status === "done"
      ? measured
        ? `done, ${measured}`
        : "done"
      : block.status === "planned"
        ? METHOD_LABELS[block.method].toLowerCase()
        : block.status;
  return `${dayLabel(start.date)}, ${blockTitle(block)}, ${clock(start.minutes)} to ${clock(end.minutes)}, ${state}`;
}

/** Whether the block is happening now (planned, started, not ended). */
export function isNow(block: PlanBlock, now: number): boolean {
  return (
    block.status === "planned" && Date.parse(block.start) <= now && now < Date.parse(block.end)
  );
}
