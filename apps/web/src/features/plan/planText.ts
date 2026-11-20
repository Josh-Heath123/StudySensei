import type { PlanBlock } from "./api";

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

/** Whether the block is happening now (planned, started, not ended). */
export function isNow(block: PlanBlock, now: number): boolean {
  return (
    block.status === "planned" && Date.parse(block.start) <= now && now < Date.parse(block.end)
  );
}
