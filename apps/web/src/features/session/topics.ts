import type { TopicNode } from "../modules/api";

export type FlatTopic = { id: string; name: string; depth: number };

/** The topic tree in reading order, with each topic's depth (for indenting). */
export function flattenTopics(nodes: readonly TopicNode[], depth = 0): FlatTopic[] {
  return nodes.flatMap((node) => [
    { id: node.id, name: node.name, depth },
    ...flattenTopics(node.children, depth + 1),
  ]);
}

export function findTopicName(nodes: readonly TopicNode[], id: string | null): string | null {
  if (id === null) return null;
  return flattenTopics(nodes).find((topic) => topic.id === id)?.name ?? null;
}
