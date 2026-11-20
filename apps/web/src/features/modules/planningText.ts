import type { components } from "@/lib/api/schema";

export type Workload = components["schemas"]["WorkloadOut"];
type TopicNode = components["schemas"]["TopicNodeOut"];

/** A topic anywhere in the tree, by id. */
export function findTopic(nodes: TopicNode[], id: string): TopicNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findTopic(node.children, id);
    if (found) return found;
  }
  return null;
}

/** What each starting-confidence rating means (self-rated, never inferred). */
export const CONFIDENCE_LABELS: Record<number, string> = {
  1: "New to me",
  2: "Shaky",
  3: "Getting there",
  4: "Solid",
  5: "Could teach it",
};

/** An exact duration: "45 min", "2 h", "1 h 30 min". */
export function exactDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** What the estimate was made from: "18 slides", "2 pages", "18 slides and 2 pages". */
export function pagesText(workload: Workload): string {
  const parts = [];
  if (workload.slide_pages > 0) parts.push(plural(workload.slide_pages, "slide", "slides"));
  if (workload.text_pages > 0) parts.push(plural(workload.text_pages, "page", "pages"));
  return parts.join(" and ");
}

/** The workload, labelled: "≈ 2 h 15, estimated from 18 slides" or "1 h 30 min (yours)". */
export function workloadText(workload: Workload): string {
  if (workload.minutes === null) return "No estimate yet: no slides or notes are linked.";
  if (workload.source === "yours") return `${exactDuration(workload.minutes)} (yours)`;
  return `≈ ${planDuration(workload.minutes)}, estimated from ${pagesText(workload)}`;
}

/** The short form for a topic row: "≈ 2 h 15" or "1 h 30 min (yours)"; null with nothing. */
export function workloadShort(workload: Workload): string | null {
  if (workload.minutes === null) return null;
  return workload.source === "yours"
    ? `${exactDuration(workload.minutes)} (yours)`
    : `≈ ${planDuration(workload.minutes)}`;
}

/** "Confidence 3/5", or "Not rated". */
export function confidenceText(confidence: number | null | undefined): string {
  return confidence ? `Confidence ${confidence}/5` : "Not rated";
}

export type SubtreeWorkload = components["schemas"]["SubtreeWorkloadOut"];

/** The planner's format: "40 min", "3 h", "7 h 15". */
export function planDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${String(rest).padStart(2, "0")}`;
}

/**
 * A chapter's whole workload, as the planner counts it when the chapter is in an assessment
 * (decision 0019): "≈ 7 h with its 4 subtopics (estimated from 72 slides and 34 pages)".
 */
export function subtreeWorkloadText(workload: SubtreeWorkload): string {
  const subtopics = plural(workload.subtopics, "subtopic", "subtopics");
  if (workload.minutes === null) {
    return `No estimate with its ${subtopics} yet: no slides or notes are linked to any of them.`;
  }
  if (workload.source === "yours") {
    return `${exactDuration(workload.minutes)} for it and its ${subtopics} (yours)`;
  }
  return `≈ ${planDuration(workload.minutes)} with its ${subtopics} (estimated from ${pagesText(workload)})`;
}
