import { daysUntil, isPast } from "@/lib/dates";

import type { Module } from "../modules/api";
import { KIND_LABELS, type Assessment } from "../modules/assessments/api";
import type { Task } from "../modules/tasks/api";

export type Deadline = {
  key: string;
  type: "assessment" | "task";
  id: string;
  title: string;
  dueAt: string;
  module: Pick<Module, "id" | "code" | "colour">;
  /** "Exam", "Assignment"… for assessments; "Task" or "Task · Assignment 2" for tasks. */
  label: string;
  overdue: boolean;
};

export type GroupKey = "overdue" | "today" | "week" | "later";

export type DeadlineGroup = { key: GroupKey; label: string; items: Deadline[] };

const GROUP_LABELS: Record<GroupKey, string> = {
  overdue: "Overdue",
  today: "Today",
  week: "Next 7 days",
  later: "Later",
};

function groupOf(dueAt: string, now: Date): GroupKey {
  if (isPast(dueAt, now)) return "overdue";
  const days = daysUntil(dueAt, now);
  if (days === 0) return "today";
  return days <= 7 ? "week" : "later";
}

/**
 * Open assessments and tasks across all modules, soonest first, grouped into
 * Overdue / Today / Next 7 days / Later (empty groups are left out).
 * Items without a due date aren't deadlines; tasks without one are counted instead.
 * Callers pass only open items (upcoming assessments, unfinished tasks).
 */
export function buildDeadlines(
  assessments: Assessment[],
  tasks: Task[],
  modules: Module[],
  now: Date = new Date(),
): { groups: DeadlineGroup[]; undatedTasks: number } {
  const moduleById = new Map(modules.map((m) => [m.id, m]));
  const assessmentTitle = new Map(assessments.map((a) => [a.id, a.title]));
  const items: Deadline[] = [];

  for (const a of assessments) {
    const module = moduleById.get(a.module_id);
    if (!a.due_at || !module) continue;
    items.push({
      key: `assessment:${a.id}`,
      type: "assessment",
      id: a.id,
      title: a.title,
      dueAt: a.due_at,
      module,
      label: KIND_LABELS[a.kind],
      overdue: isPast(a.due_at, now),
    });
  }

  let undatedTasks = 0;
  for (const t of tasks) {
    const module = moduleById.get(t.module_id);
    if (!module) continue;
    if (!t.due_at) {
      undatedTasks += 1;
      continue;
    }
    const forTitle = t.assessment_id ? assessmentTitle.get(t.assessment_id) : undefined;
    items.push({
      key: `task:${t.id}`,
      type: "task",
      id: t.id,
      title: t.title,
      dueAt: t.due_at,
      module,
      label: forTitle ? `Task · ${forTitle}` : "Task",
      overdue: isPast(t.due_at, now),
    });
  }

  items.sort((a, b) => Date.parse(a.dueAt) - Date.parse(b.dueAt) || a.title.localeCompare(b.title));

  const groups = new Map<GroupKey, Deadline[]>();
  for (const item of items) {
    const key = groupOf(item.dueAt, now);
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const order: GroupKey[] = ["overdue", "today", "week", "later"];
  return {
    groups: order
      .filter((key) => groups.has(key))
      .map((key) => ({ key, label: GROUP_LABELS[key], items: groups.get(key)! })),
    undatedTasks,
  };
}

/** A countdown tile on Today: whole days until an upcoming assessment. */
export type Countdown = {
  id: string;
  title: string;
  dueAt: string;
  /** Calendar days from today (0 = due today). */
  days: number;
  module: Pick<Module, "id" | "code" | "colour">;
};

/**
 * The next `limit` dated assessments that haven't passed yet, soonest first. Overdue
 * ones are left out here: they're in the deadline list, labelled "Overdue".
 */
export function countdowns(
  assessments: Assessment[],
  modules: Module[],
  now: Date = new Date(),
  limit = 3,
): Countdown[] {
  const moduleById = new Map(modules.map((m) => [m.id, m]));
  const upcoming: Countdown[] = [];
  for (const a of assessments) {
    const module = moduleById.get(a.module_id);
    if (!a.due_at || !module || isPast(a.due_at, now)) continue;
    upcoming.push({
      id: a.id,
      title: a.title,
      dueAt: a.due_at,
      days: daysUntil(a.due_at, now),
      module,
    });
  }
  return upcoming
    .sort((a, b) => Date.parse(a.dueAt) - Date.parse(b.dueAt) || a.title.localeCompare(b.title))
    .slice(0, limit);
}
