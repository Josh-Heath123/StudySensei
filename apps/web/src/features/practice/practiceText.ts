import type { TopicMastery } from "@/features/modules/api";

import type { Generation, PracticeItem, QueueCounts } from "./api";

export type Grade = 1 | 2 | 3 | 4;

export const GRADES: { grade: Grade; label: string }[] = [
  { grade: 1, label: "Again" },
  { grade: 2, label: "Hard" },
  { grade: 3, label: "Good" },
  { grade: 4, label: "Easy" },
];

/** Under "Check with AI" (ADR 0029): exactly what is sent. */
export const MARKING_PRIVACY =
  "Sends your answer and the reference answer to the AI to check it. Nothing else about you.";

export const GRADE_LABELS: Record<Grade, string> = { 1: "Again", 2: "Hard", 3: "Good", 4: "Easy" };

/**
 * The grade a tick list suggests (ADR 0029), the same rule the server applies to an AI
 * marking: every key point ticked suggests Good, at least half Hard, fewer Again. Nothing
 * suggests Easy: that's the student's call.
 */
export function suggestFromTicks(ticked: number, total: number): 1 | 2 | 3 {
  if (total < 1) return 1;
  if (ticked >= total) return 3;
  return ticked / total >= 0.5 ? 2 : 1;
}

/** "now", "in 1 min", "in 3 h", "in 2 days" (rounded, never "in 0 min"). */
export function fromNow(iso: string, now: Date): string {
  const minutes = (new Date(iso).getTime() - now.getTime()) / 60_000;
  if (minutes < 1) return "now";
  if (minutes < 60) return `in ${Math.round(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 24) return `in ${Math.round(hours)} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? "in 1 day" : `in ${days} days`;
}

/** "4 due now · 12 new today", leaving out a zero; "" when there's nothing. */
export function countsLine(counts: Pick<QueueCounts, "due_now" | "new_today_left">): string {
  const parts = [];
  if (counts.due_now > 0) parts.push(`${counts.due_now} due now`);
  if (counts.new_today_left > 0) parts.push(`${counts.new_today_left} new today`);
  return parts.join(" · ");
}

const STATE_NAMES = {
  new: "New",
  learning: "Learning",
  review: "Review",
  relearning: "Relearning",
} as const;

/** "New", "Learning · due in 10 min", "Review · due in 4 days", "Review · due now". */
export function memoryText(memory: PracticeItem["memory"], now: Date): string {
  const name = STATE_NAMES[memory.state];
  if (memory.state === "new" || !memory.due) return name;
  return `${name} · due ${fromNow(memory.due, now)}`;
}

/** A source chip: "CH05 p14". A title that starts with a code (CH05, L3, W12) is shortened
 * to it; any other is cut at 16 characters. */
export function sourceChip(title: string, page: number): string {
  const code = /^([A-Za-z]{1,4}\s?\d{1,3})\b/.exec(title.trim());
  const short = code
    ? code[1]!.replace(/\s/, "")
    : title.length > 16
      ? `${title.slice(0, 15).trimEnd()}…`
      : title;
  return `${short} p${page}`;
}

/** Weakest first by value, ties by name. Every topic is listed, with or without a band. */
export function weakestFirst<T extends Pick<TopicMastery, "value" | "name">>(topics: T[]): T[] {
  return [...topics].sort((a, b) => a.value - b.value || a.name.localeCompare(b.name));
}

/** The newest generation's state, for the button beside it. */
export function generationText(generation: Generation | undefined): string | null {
  if (!generation) return null;
  switch (generation.status) {
    case "queued":
      return "Queued…";
    case "running":
      return "Writing practice…";
    case "succeeded":
      return generation.produced === 0
        ? "None written: nothing passed the checks."
        : `${generation.produced} written`;
    case "failed":
      return generation.error ?? "Generation failed.";
  }
}

/** The share of grades that were right (Good or Easy), as a whole percent. */
export function shareRight(grades: Grade[]): number {
  if (grades.length === 0) return 0;
  return Math.round((100 * grades.filter((g) => g >= 3).length) / grades.length);
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

type TreeNode = { id: string; name: string; children: TreeNode[] };

/** A topic tree as options in course order, each with its depth (for an indented select). */
export function flattenTopics(
  nodes: TreeNode[],
  depth = 0,
): { id: string; name: string; depth: number }[] {
  return nodes.flatMap((node) => [
    { id: node.id, name: node.name, depth },
    ...flattenTopics(node.children, depth + 1),
  ]);
}

/** Key points typed one per line: trimmed, blanks dropped. */
export function keyPointLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}
