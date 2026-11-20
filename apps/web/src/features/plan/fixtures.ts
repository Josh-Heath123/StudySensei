import type { Plan, PlanBlock } from "./api";

/** A planned study block (override anything). Times are ISO strings. */
export function aBlock(overrides: Partial<PlanBlock> = {}): PlanBlock {
  const start = overrides.start ?? "2026-11-13T18:00:00Z";
  const end = overrides.end ?? "2026-11-13T18:50:00Z";
  return {
    id: "b1",
    start: "2026-11-13T18:00:00Z",
    end: "2026-11-13T18:50:00Z",
    minutes: 50,
    planned_start: start,
    planned_end: end,
    module_id: "m1",
    module_code: "COS330",
    module_colour: "#8FB8FF",
    assessment_id: "a1",
    assessment_title: "Exam",
    topic_id: "t1",
    topic_name: "Ch2 Cryptography",
    kind: "study",
    reason: "workload",
    method: "practice",
    reason_text: "≈ 4 h estimated from 40 slides; not studied yet (measured: no sessions).",
    method_text: "Quiz yourself first (Quiz me), then re-read what you missed.",
    status: "planned",
    status_changed_at: null,
    fixed: false,
    pinned: false,
    linked_session_id: null,
    session_minutes: null,
    actions: { start: true, skip: true, move: true },
    ...overrides,
  };
}

/** A plan version with these blocks (and a report that fits). */
export function aPlan(blocks: PlanBlock[] = [], overrides: Partial<Plan> = {}): Plan {
  return {
    number: 2,
    trigger: "skip",
    summary: "You skipped Ch1 Overview (Thu 12 Nov, 18:00): its time is placed again.",
    generated_at: "2026-11-13T07:43:00Z",
    checked_at: "2026-11-13T07:43:00Z",
    timezone: "UTC",
    days: 28,
    first: "2026-11-09",
    last: "2026-11-15",
    replan_pending: false,
    blocks,
    report: {
      overall: {
        required_minutes: 240,
        planned_minutes: 250,
        short_minutes: 0,
        review_minutes: 50,
        free_minutes: 1260,
        booked_minutes: 300,
        status: "fits",
        deadline: "2026-11-20T09:00:00Z",
        line: "You need 4 h before 20 Nov and have 21 h.",
      },
      assessments: [
        {
          assessment_id: "a1",
          title: "Exam",
          module_code: "COS330",
          due_at: "2026-11-20T09:00:00Z",
          line: "COS330 Exam (20 Nov): needs 4 h, 4 h 10 planned, 21 h free before it: fits.",
          required_minutes: 240,
          planned_minutes: 250,
          short_minutes: 0,
          review_minutes: 50,
          free_minutes: 1260,
          booked_minutes: 300,
          status: "fits",
          topics: [],
          issues: [],
          planned_with: [],
        },
      ],
      later: [],
      levers: [],
      basis: "Needed time is estimated.",
    },
    ...overrides,
  };
}

export const UTC_SETTINGS = { timezone: "UTC", daily_study_cap_minutes: 180 };
