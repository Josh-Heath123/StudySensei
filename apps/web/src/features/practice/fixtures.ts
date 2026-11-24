import { aMastery } from "@/features/modules/fixtures";

import type {
  AiMarking,
  Generation,
  ModuleMastery,
  PracticeItem,
  PracticeSettings,
  Preview,
  Queue,
  QueueCounts,
  ReviewResult,
} from "./api";

const CREATED = "2026-11-20T09:00:00Z";

/** A new flashcard of the student's own, on module m1's topic t1. */
export function anItem(overrides: Partial<PracticeItem> = {}): PracticeItem {
  return {
    id: "i1",
    module_id: "m1",
    topic_id: "t1",
    kind: "flashcard",
    prompt: "What does a hash table store?",
    answer: "Key and value pairs, found by hashing the key.",
    key_points: null,
    origin: "user",
    status: "active",
    reject_reason: null,
    provider: null,
    model: null,
    generation_id: null,
    created_at: CREATED,
    updated_at: CREATED,
    sources: [],
    pages: [],
    sources_missing: false,
    memory: {
      state: "new",
      due: null,
      stability: null,
      difficulty: null,
      retrievability: null,
      reps: 0,
      lapses: 0,
    },
    ...overrides,
  };
}

/** A short-answer question with three key points, cited from CH05 p14. */
export function aShortAnswer(overrides: Partial<PracticeItem> = {}): PracticeItem {
  return anItem({
    id: "i2",
    kind: "short_answer",
    prompt: "Why does a hash table need a good hash function?",
    answer: "It spreads keys evenly, so buckets stay short and lookups stay fast.",
    key_points: ["Spreads keys evenly", "Keeps buckets short", "Keeps lookups fast"],
    origin: "ai",
    sources: [
      { label: "S1", material_id: "mat1", material_title: "CH05 Hashing", page_number: 14 },
    ],
    pages: [{ material_id: "mat1", material_title: "CH05 Hashing", page_number: 14 }],
    ...overrides,
  });
}

export function aCounts(overrides: Partial<QueueCounts> = {}): QueueCounts {
  return {
    due_now: 0,
    new_today_left: 0,
    new_allowance_left: 20,
    new_total: 0,
    next_due_at: null,
    ...overrides,
  };
}

export function aQueue(items: PracticeItem[] = [], counts: Partial<QueueCounts> = {}): Queue {
  return { items, counts: aCounts(counts) };
}

export function aPreview(): Preview {
  return {
    at: "2026-11-23T10:00:00Z",
    options: [
      { grade: 1, name: "again", due: "2026-11-23T10:01:00Z", interval: "1 min" },
      { grade: 2, name: "hard", due: "2026-11-23T10:06:00Z", interval: "6 min" },
      { grade: 3, name: "good", due: "2026-11-23T10:10:00Z", interval: "10 min" },
      { grade: 4, name: "easy", due: "2026-12-01T10:00:00Z", interval: "8 days" },
    ],
  };
}

/** The AI found two of the three key points: partly right, Hard suggested. */
export function aMarking(overrides: Partial<AiMarking> = {}): AiMarking {
  return {
    coverage: [
      { index: 1, key_point: "Spreads keys evenly", covered: true },
      { index: 2, key_point: "Keeps buckets short", covered: true },
      { index: 3, key_point: "Keeps lookups fast", covered: false },
    ],
    verdict: "partly",
    suggested_grade: 2,
    feedback: "You explain the spreading and the buckets; say why that keeps lookups fast.",
    model: "gemini/flash",
    ...overrides,
  };
}

export function aReviewResult(grade: number, counts: Partial<QueueCounts> = {}): ReviewResult {
  return {
    review: {
      id: `r${grade}`,
      item_id: "i1",
      reviewed_at: "2026-11-23T10:00:00Z",
      grade,
      marked_by: "self",
      duration_ms: 1000,
      answer_text: null,
      scheduled_days: 0,
      desired_retention: 0.9,
      fsrs_version: "fsrs 6.3.3",
      ai_marking: null,
      after: { state: "learning", due: "2026-11-23T10:10:00Z" },
    },
    scheduled: { state: "learning", due: "2026-11-23T10:10:00Z", scheduled_days: 0 },
    counts: aCounts(counts),
  };
}

export function aGeneration(overrides: Partial<Generation> = {}): Generation {
  return {
    id: "g1",
    module_id: "m1",
    topic_id: "t1",
    status: "succeeded",
    requested: 8,
    produced: 8,
    dropped: {},
    provider: "gemini",
    model: "flash",
    error: null,
    created_at: CREATED,
    finished_at: CREATED,
    ...overrides,
  };
}

export function aModuleMastery(
  moduleId = "m1",
  topics = [aMastery({ topic_id: "t1", name: "Hashing" })],
): ModuleMastery {
  return { module_id: moduleId, at: "2026-11-23T10:00:00Z", topics };
}

export const PRACTICE_SETTINGS: PracticeSettings = { new_per_day: 20, desired_retention: 0.9 };
