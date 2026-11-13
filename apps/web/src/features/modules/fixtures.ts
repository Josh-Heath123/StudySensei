import { toIso } from "@/lib/dates";

import type { Module, TopicNode } from "./api";
import type { Assessment } from "./assessments/api";
import type { Task } from "./tasks/api";

export function aModule(overrides: Partial<Module> = {}): Module {
  return {
    id: "m1",
    code: "COS330",
    name: "Software Architecture",
    colour: "#FF7A3D",
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

export function anAssessment(overrides: Partial<Assessment> = {}): Assessment {
  return {
    id: "a1",
    module_id: "m1",
    title: "Semester test 1",
    kind: "test",
    due_at: toIso("2026-11-20", "09:00"),
    weight: 30,
    status: "upcoming",
    notes: null,
    topic_ids: ["p"],
    created_at: "2026-11-12T10:00:00Z",
    updated_at: "2026-11-12T10:00:00Z",
    ...overrides,
  };
}

export function aTask(overrides: Partial<Task> = {}): Task {
  return {
    id: "t1",
    module_id: "m1",
    assessment_id: null,
    title: "Read chapter 4",
    due_at: null,
    status: "todo",
    completed_at: null,
    notes: null,
    created_at: "2026-11-12T10:00:00Z",
    updated_at: "2026-11-12T10:00:00Z",
    ...overrides,
  };
}
