import type { ReviewStats, TopicNode } from "./api";

/** "Review: 40 kept, 6 renamed, 3 merged, 2 dismissed", or null before any review. */
export function reviewLine(stats: ReviewStats | undefined): string | null {
  if (!stats) return null;
  const { kept, renamed, merged, dismissed } = stats;
  if (kept + renamed + merged + dismissed === 0) return null;
  return `Review: ${kept} kept, ${renamed} renamed, ${merged} merged, ${dismissed} dismissed`;
}

/** Reviewed and total AI topics, for "12 of 53 reviewed". */
export function reviewProgress(stats: ReviewStats | undefined): { done: number; total: number } {
  if (!stats) return { done: 0, total: 0 };
  const done = stats.kept + stats.renamed + stats.merged + stats.dismissed;
  return { done, total: done + stats.unreviewed };
}

/** The tree cut down to topics still marked AI, with the ancestors that hold them. */
export function unreviewedOnly(nodes: TopicNode[]): TopicNode[] {
  return nodes.flatMap((node) => {
    const children = unreviewedOnly(node.children);
    return node.source === "ai" || children.length > 0 ? [{ ...node, children }] : [];
  });
}

/** Descendants still marked AI (dismissed together with their parent). */
export function aiDescendants(node: TopicNode): number {
  return node.children.reduce(
    (sum, child) => sum + (child.source === "ai" ? 1 : 0) + aiDescendants(child),
    0,
  );
}

export type TopicChoice = { id: string; name: string; depth: number };

/** Every topic a topic can be merged into: all but itself and its own subtopics. */
export function mergeTargets(nodes: TopicNode[], excluded: string, depth = 0): TopicChoice[] {
  return nodes.flatMap((node) =>
    node.id === excluded
      ? []
      : [
          { id: node.id, name: node.name, depth },
          ...mergeTargets(node.children, excluded, depth + 1),
        ],
  );
}
