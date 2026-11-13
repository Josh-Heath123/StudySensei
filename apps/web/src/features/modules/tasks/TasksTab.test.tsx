import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { toIso } from "@/lib/dates";
import { json, mockApi, noContent, type ApiCall } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule } from "../fixtures";
import type { Task } from "./api";

function aTask(overrides: Partial<Task> = {}): Task {
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

const ASSIGNMENT = {
  id: "a1",
  module_id: "m1",
  title: "Assignment 2",
  kind: "assignment" as const,
  due_at: null,
  weight: 20,
  status: "upcoming" as const,
  notes: null,
  topic_ids: [],
  created_at: "2026-11-12T10:00:00Z",
  updated_at: "2026-11-12T10:00:00Z",
};

function renderTab(tasks: Task[]) {
  const api = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/tasks": () => tasks,
    "GET /modules/:id/assessments": () => [ASSIGNMENT],
    "POST /modules/:id/tasks": (call) => json(aTask(call.body as object), 201),
    "PATCH /tasks/:id": (call) => aTask(call.body as object),
    "DELETE /tasks/:id": () => noContent(),
  });
  renderApp("/modules/m1?tab=tasks");
  return { ...api, user: userEvent.setup() };
}

const patches = (calls: ApiCall[]) => calls.filter((c) => c.method === "PATCH");

const TASKS = [
  aTask({ id: "t1", title: "Draft report", assessment_id: "a1", due_at: "2020-01-01T10:00:00Z" }),
  aTask({ id: "t2", title: "Read chapter 4", status: "in_progress" }),
  aTask({ id: "t3", title: "Set up repo", status: "done", completed_at: "2026-11-10T10:00:00Z" }),
];

test("lists open tasks, with their assessment and overdue state; done ones on request", async () => {
  const { user } = renderTab(TASKS);

  const list = await screen.findByRole("list", { name: "Tasks" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByText("2 open · 1 done")).toBeInTheDocument();
  const draft = within(list).getAllByRole("listitem")[0]!;
  expect(draft).toHaveTextContent("For Assignment 2");
  expect(draft).toHaveTextContent("Overdue");

  await user.click(screen.getByLabelText("Show done"));
  expect(within(list).getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByLabelText("Done: Set up repo")).toBeChecked();
});

test("the checkbox marks done and reopens; the select sets any status", async () => {
  const { calls, user } = renderTab(TASKS);

  await user.click(await screen.findByLabelText("Done: Draft report"));
  await waitFor(() => expect(patches(calls)).toHaveLength(1));
  expect(patches(calls)[0]).toMatchObject({ path: "/tasks/t1", body: { status: "done" } });

  await user.selectOptions(screen.getByLabelText("Status: Draft report"), "in_progress");
  await waitFor(() => expect(patches(calls)).toHaveLength(2));
  expect(patches(calls)[1]!.body).toEqual({ status: "in_progress" });

  await user.click(screen.getByLabelText("Show done"));
  await user.click(screen.getByLabelText("Done: Set up repo"));
  await waitFor(() => expect(patches(calls)).toHaveLength(3));
  expect(patches(calls)[2]).toMatchObject({ path: "/tasks/t3", body: { status: "todo" } });
});

test("adds a task linked to an assessment", async () => {
  const { calls, user } = renderTab([]);

  expect(await screen.findByText(/No tasks yet/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add task" }));
  const dialog = await screen.findByRole("dialog", { name: "Add task" });
  await user.type(within(dialog).getByLabelText("Task"), "Draft report");
  await user.type(within(dialog).getByLabelText("Due date"), "2026-11-25");
  await user.selectOptions(within(dialog).getByLabelText("For assessment"), "a1");
  await user.click(within(dialog).getByRole("button", { name: "Add task" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    title: "Draft report",
    assessment_id: "a1",
    due_at: toIso("2026-11-25", "23:59"),
    notes: null,
    status: "todo",
  });
});

test("edits a task, prefilled", async () => {
  const { calls, user } = renderTab(TASKS);

  await user.click(await screen.findByRole("button", { name: "Edit: Draft report" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit task" });
  expect(within(dialog).getByLabelText("For assessment")).toHaveValue("a1");
  await user.selectOptions(within(dialog).getByLabelText("For assessment"), "");
  await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(patches(calls)).toHaveLength(1));
  expect(patches(calls)[0]!.body).toMatchObject({ assessment_id: null, title: "Draft report" });
});

test("deletes after confirming", async () => {
  const { calls, user } = renderTab(TASKS);

  await user.click(await screen.findByRole("button", { name: "Delete: Read chapter 4" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete “Read chapter 4”?" });
  await user.click(within(dialog).getByRole("button", { name: "Delete task" }));

  await waitFor(() => expect(calls.find((c) => c.method === "DELETE")?.path).toBe("/tasks/t2"));
});
