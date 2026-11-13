import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { toIso } from "@/lib/dates";
import { mockApi, type ApiCall } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { Module } from "../modules/api";
import type { Assessment } from "../modules/assessments/api";
import { aModule, anAssessment, aTask } from "../modules/fixtures";
import type { Task } from "../modules/tasks/api";

// Friday 13 November 2026, 10:00 local time.
const NOW = new Date(2026, 10, 13, 10, 0);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

const HEALTHY = { status: "ok", api: "ok", database: "ok" };

function renderToday(
  data: { modules?: Module[]; assessments?: Assessment[]; tasks?: Task[] },
  reply?: (call: ApiCall) => unknown,
) {
  const api = mockApi({
    "GET /health": () => HEALTHY,
    "GET /modules": () => data.modules ?? [aModule()],
    "GET /assessments": () => data.assessments ?? [],
    "GET /tasks": () => data.tasks ?? [],
    "PATCH /tasks/:id": (call) => reply?.(call) ?? {},
    "PATCH /assessments/:id": (call) => reply?.(call) ?? {},
  });
  renderApp("/");
  return api;
}

test("with no modules, points to adding one", async () => {
  renderToday({ modules: [] });

  expect(await screen.findByText("No modules yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Add a module" })).toHaveAttribute("href", "/modules");
});

test("with nothing dated, says so and counts undated tasks", async () => {
  renderToday({
    assessments: [anAssessment({ due_at: null })],
    tasks: [aTask({ id: "t1" }), aTask({ id: "t2" })],
  });

  expect(await screen.findByText("Nothing due")).toBeInTheDocument();
  expect(screen.getByText("2 open tasks have no due date.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Go to modules" })).toHaveAttribute("href", "/modules");
});

test("asks only for upcoming assessments and unfinished tasks", async () => {
  const { fetchMock } = renderToday({});
  await screen.findByText("Nothing due");

  const urls = fetchMock.mock.calls.map(([request]) => new URL(request.url));
  const query = (path: string) =>
    urls.find((u) => u.pathname === path)?.searchParams.getAll("status");
  expect(query("/api/assessments")).toEqual(["upcoming"]);
  expect(query("/api/tasks")).toEqual(["todo", "in_progress"]);
});

test("lists deadlines across modules, soonest first, with overdue ones flagged", async () => {
  renderToday({
    modules: [aModule(), aModule({ id: "m2", code: "COS301" })],
    assessments: [
      anAssessment({ id: "a1", title: "Exam", kind: "exam", due_at: toIso("2026-11-27", "09:00") }),
      anAssessment({
        id: "a2",
        title: "Assignment 2",
        kind: "assignment",
        module_id: "m2",
        due_at: toIso("2026-11-13", "23:59"),
      }),
    ],
    tasks: [
      aTask({
        id: "t1",
        title: "Draft report",
        module_id: "m2",
        assessment_id: "a2",
        due_at: toIso("2026-11-12", "23:59"),
      }),
      aTask({ id: "t2", title: "Revise patterns", due_at: toIso("2026-11-16", "18:00") }),
    ],
  });

  const overdue = await screen.findByRole("list", { name: "Overdue" });
  const row = within(overdue).getByRole("listitem");
  expect(row).toHaveTextContent("Draft report");
  expect(row).toHaveTextContent("COS301");
  expect(row).toHaveTextContent("Task · Assignment 2");
  expect(row).toHaveTextContent("yesterday");
  expect(within(row).getByText("Overdue")).toBeInTheDocument();
  expect(within(row).getByRole("link", { name: "Draft report" })).toHaveAttribute(
    "href",
    "/modules/m2?tab=tasks",
  );

  const titles = (name: string) =>
    within(screen.getByRole("list", { name }))
      .getAllByRole("link")
      .map((link) => link.textContent);
  expect(titles("Today")).toEqual(["Assignment 2"]);
  expect(titles("Next 7 days")).toEqual(["Revise patterns"]);
  expect(titles("Later")).toEqual(["Exam"]);
  expect(screen.getByRole("link", { name: "Exam" })).toHaveAttribute(
    "href",
    "/modules/m1?tab=assessments",
  );
  // Only overdue items are flagged.
  expect(screen.getAllByText("Overdue", { selector: "[data-slot=badge]" })).toHaveLength(1);
});

test("ticking a task marks it done", async () => {
  const { calls } = renderToday({
    tasks: [aTask({ title: "Draft report", due_at: toIso("2026-11-14", "12:00") })],
  });
  const user = userEvent.setup();

  await user.click(await screen.findByRole("checkbox", { name: "Done: Draft report" }));

  await waitFor(() =>
    expect(calls).toContainEqual({
      method: "PATCH",
      path: "/tasks/t1",
      body: { status: "done" },
    }),
  );
});

test("an overdue assessment can be marked completed", async () => {
  const { calls } = renderToday({
    assessments: [anAssessment({ title: "Semester test 1", due_at: toIso("2026-11-10", "09:00") })],
  });
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Mark completed" }));

  await waitFor(() =>
    expect(calls).toContainEqual({
      method: "PATCH",
      path: "/assessments/a1",
      body: { status: "completed" },
    }),
  );
});

test("a failed update is shown", async () => {
  renderToday(
    { tasks: [aTask({ title: "Draft report", due_at: toIso("2026-11-14", "12:00") })] },
    () => new Response(JSON.stringify({ detail: "Task not found" }), { status: 404 }),
  );
  const user = userEvent.setup();

  await user.click(await screen.findByRole("checkbox", { name: "Done: Draft report" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Task not found");
});

test("a failed load is shown", async () => {
  mockApi({
    "GET /health": () => HEALTHY,
    "GET /modules": () => [aModule()],
    "GET /assessments": () => [],
    "GET /tasks": () => new Response(JSON.stringify({ detail: "Boom" }), { status: 500 }),
  });
  renderApp("/");

  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load deadlines");
});
