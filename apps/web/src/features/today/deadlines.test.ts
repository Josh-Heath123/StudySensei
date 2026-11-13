import { toIso } from "@/lib/dates";

import { aModule, anAssessment, aTask } from "../modules/fixtures";
import { buildDeadlines } from "./deadlines";

// Friday 13 November 2026, 10:00 local time.
const NOW = new Date(2026, 10, 13, 10, 0);
const at = (day: number, time: string) => toIso(`2026-11-${String(day).padStart(2, "0")}`, time);

const MODULES = [aModule(), aModule({ id: "m2", code: "COS301", colour: "#FF9500" })];

function titlesByGroup(result: ReturnType<typeof buildDeadlines>) {
  return Object.fromEntries(result.groups.map((g) => [g.label, g.items.map((i) => i.title)]));
}

test("groups open items across modules into overdue, today, next 7 days and later, soonest first", () => {
  const assessments = [
    anAssessment({ id: "exam", title: "Exam", kind: "exam", due_at: at(21, "09:00") }),
    anAssessment({ id: "a2", title: "Assignment 2", kind: "assignment", due_at: at(13, "23:59") }),
    anAssessment({ id: "st", title: "Morning test", module_id: "m2", due_at: at(13, "08:00") }),
    anAssessment({ id: "p", title: "Project", kind: "project", due_at: at(20, "23:59") }),
  ];
  const tasks = [
    aTask({ id: "t1", title: "Draft report", due_at: at(12, "23:59"), assessment_id: "a2" }),
    aTask({ id: "t2", title: "Revise ch. 4", module_id: "m2", due_at: at(16, "18:00") }),
  ];

  const result = buildDeadlines(assessments, tasks, MODULES, NOW);

  expect(titlesByGroup(result)).toEqual({
    Overdue: ["Draft report", "Morning test"],
    Today: ["Assignment 2"],
    // 20 Nov is 7 days away (still "next 7 days"); 21 Nov is 8.
    "Next 7 days": ["Revise ch. 4", "Project"],
    Later: ["Exam"],
  });
  expect(result.groups.map((g) => g.key)).toEqual(["overdue", "today", "week", "later"]);
});

test("labels, overdue flags and module details", () => {
  const assessments = [
    anAssessment({ id: "a2", title: "Assignment 2", kind: "assignment", due_at: at(20, "23:59") }),
  ];
  const tasks = [
    aTask({ id: "t1", title: "Draft", due_at: at(12, "12:00"), assessment_id: "a2" }),
    aTask({ id: "t2", title: "Solo", module_id: "m2", due_at: at(14, "12:00") }),
  ];

  const items = buildDeadlines(assessments, tasks, MODULES, NOW).groups.flatMap((g) => g.items);

  expect(items.map((i) => [i.title, i.type, i.label, i.overdue, i.module.code])).toEqual([
    ["Draft", "task", "Task · Assignment 2", true, "COS330"],
    ["Solo", "task", "Task", false, "COS301"],
    ["Assignment 2", "assessment", "Assignment", false, "COS330"],
  ]);
});

test("undated items aren't deadlines; undated tasks are counted", () => {
  const result = buildDeadlines(
    [anAssessment({ due_at: null })],
    [aTask({ id: "t1" }), aTask({ id: "t2" })],
    MODULES,
    NOW,
  );

  expect(result).toEqual({ groups: [], undatedTasks: 2 });
});

test("nothing at all gives no groups", () => {
  expect(buildDeadlines([], [], MODULES, NOW)).toEqual({ groups: [], undatedTasks: 0 });
});
