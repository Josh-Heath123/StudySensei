import type { TopicMove, TopicNode } from "./api";

export type MoveAction = "up" | "down" | "indent" | "outdent";

/**
 * Where each move button sends a topic. Positions are indexes among the new
 * siblings *excluding* the moved topic, matching POST /topics/{id}/move.
 */
export function moveTarget(
  action: MoveAction,
  siblings: TopicNode[],
  index: number,
  parent: TopicNode | null,
): TopicMove | null {
  const topic = siblings[index]!;
  switch (action) {
    case "up":
      return index > 0 ? { parent_id: topic.parent_id, position: index - 1 } : null;
    case "down":
      return index < siblings.length - 1
        ? { parent_id: topic.parent_id, position: index + 1 }
        : null;
    case "indent": {
      // Becomes the last child of the sibling above it.
      const above = siblings[index - 1];
      return above ? { parent_id: above.id, position: above.children.length } : null;
    }
    case "outdent":
      // Lands right after its current parent.
      return parent ? { parent_id: parent.parent_id, position: parent.position + 1 } : null;
  }
}
