import { toIso } from "@/lib/dates";

import type { AiStatus, Module, TopicMapStatus, TopicMastery, TopicNode } from "./api";
import type { Assessment } from "./assessments/api";
import type { SessionRow } from "./sessions/api";
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
    linked_pages: 0,
    confidence: null,
    workload: { minutes: null, source: "none", slide_pages: 0, text_pages: 0 },
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

export function aSession(overrides: Partial<SessionRow> = {}): SessionRow {
  return {
    id: "s1",
    module_id: "m1",
    topic_id: null,
    plan_block_id: null,
    state: "ended",
    started_at: "2026-11-12T08:00:00Z",
    ended_at: "2026-11-12T09:00:00Z",
    last_event_at: "2026-11-12T09:00:00Z",
    active_seconds: 50 * 60,
    break_seconds: 10 * 60,
    focus_rating: 4,
    covered_notes: null,
    reflected_at: "2026-11-12T09:01:00Z",
    topic_ratings: [],
    created_at: "2026-11-12T08:00:00Z",
    updated_at: "2026-11-12T09:01:00Z",
    ...overrides,
  };
}

/** A topic map status: by default two materials, none analysed, nothing running. */
export function aTopicMap(overrides: Partial<TopicMapStatus> = {}): TopicMapStatus {
  return {
    eligible: 2,
    analysed: 0,
    pending: 0,
    failed: 0,
    merging: false,
    waiting_until: null,
    last_error: null,
    merged_at: null,
    review: { kept: 0, renamed: 0, merged: 0, dismissed: 0, unreviewed: 0 },
    ...overrides,
  };
}

/** /ai/status with or without a provider configured (only what the UI reads). */
export function anAiStatus(available = true): AiStatus {
  return { available, providers: [], roles: {}, models: [] };
}

/** A topic with too little practice for a band: the "not enough" sentence. */
export function aMastery(overrides: Partial<TopicMastery> = {}): TopicMastery {
  return {
    topic_id: "q",
    parent_id: null,
    name: "Queues",
    value: 0.5,
    label: "estimated",
    status: "not_enough",
    band: null,
    components: { recall: null, accuracy: null, prior: 0.5, weight: 0, recall_weight: 0 },
    samples: {
      items_reviewed: 0,
      items_active: 0,
      attempts: 0,
      quiz_answers: 0,
      reviews: 0,
      days_spanned: 0,
      rating_source: "none",
    },
    basis: "Not enough practice yet: 0 of 3 attempts. With no rating yet, 50 % is assumed for now.",
    ...overrides,
  };
}
