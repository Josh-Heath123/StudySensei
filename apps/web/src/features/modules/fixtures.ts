import type { Module, TopicNode } from "./api";

export function aModule(overrides: Partial<Module> = {}): Module {
  return {
    id: "m1",
    code: "COS330",
    name: "Software Architecture",
    colour: "#007AFF",
    semester: "2026-S2",
    created_at: "2026-11-12T10:00:00Z",
    updated_at: "2026-11-12T10:00:00Z",
    ...overrides,
  };
}

export function aTopic(
  id: string,
  name: string,
  children: TopicNode[] = [],
  overrides: Partial<TopicNode> = {},
): TopicNode {
  return {
    id,
    module_id: "m1",
    parent_id: null,
    name,
    description: null,
    position: 0,
    source: "user",
    children: children.map((child, i) => ({ ...child, parent_id: id, position: i })),
    ...overrides,
  };
}

/** Root topics with positions filled in. */
export function roots(...topics: TopicNode[]): TopicNode[] {
  return topics.map((topic, i) => ({ ...topic, position: i }));
}
