import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { toIso } from "@/lib/dates";
import { json, mockApi, noContent, type ApiCall } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule, anAssessment, aTopic, roots } from "../fixtures";
import type { Assessment } from "./api";

const TREE = roots(aTopic("p", "Patterns", [aTopic("c", "Creational")]), aTopic("q", "Queues"));

function renderTab(assessments: Assessment[], reply?: (call: ApiCall) => unknown) {
  const api = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => TREE,
    "GET /modules/:id/assessments": () => assessments,
    "POST /modules/:id/assessments": (call) =>
      reply?.(call) ?? json(anAssessment(call.body as object), 201),
    "PATCH /assessments/:id": (call) => reply?.(call) ?? anAssessment(call.body as object),
    "DELETE /assessments/:id": () => noContent(),
  });
  renderApp("/modules/m1");
  return { ...api, user: userEvent.setup() };
}

const sent = (calls: ApiCall[], method: string) => calls.find((c) => c.method === method);

test("lists assessments with weight, topics and the weight total", async () => {
  renderTab([
    anAssessment(),
    anAssessment({ id: "a2", title: "Exam", kind: "exam", weight: 60, topic_ids: [] }),
    anAssessment({ id: "a3", title: "Old quiz", weight: 10, status: "cancelled" }),
  ]);

  const list = await screen.findByRole("list", { name: "Assessments" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Semester test 1");
  expect(rows[0]).toHaveTextContent("Fri 20 Nov, 09:00");
  expect(rows[0]).toHaveTextContent("1 topic");
  expect(rows[0]).toHaveTextContent("30%");
  expect(rows[1]).toHaveTextContent("No topics");
  expect(rows[2]).toHaveTextContent("Cancelled");
  // The cancelled quiz doesn't count.
  expect(screen.getByText(/Weights total/)).toHaveTextContent("Weights total 90% (not 100%)");
});

test("shows an empty state", async () => {
  renderTab([]);
  expect(await screen.findByText(/No assessments yet/)).toBeInTheDocument();
});

test("adds an assessment with a date, weight and topics", async () => {
  const { calls, user } = renderTab([]);

  await user.click(await screen.findByRole("button", { name: "Add assessment" }));
  const dialog = await screen.findByRole("dialog", { name: "Add assessment" });
  await user.type(within(dialog).getByLabelText("Title"), "Assignment 2");
  await user.selectOptions(within(dialog).getByLabelText("Kind"), "assignment");
  await user.type(within(dialog).getByLabelText("Date"), "2026-11-28");
  // An assignment defaults to the end of the day.
  expect(within(dialog).getByLabelText("Time")).toHaveValue("23:59");
  await user.type(within(dialog).getByLabelText("Weight (%)"), "40");
  await user.click(within(dialog).getByLabelText("Creational"));
  await user.click(within(dialog).getByLabelText("Queues"));
  await user.click(within(dialog).getByRole("button", { name: "Add assessment" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(sent(calls, "POST")?.body).toEqual({
    title: "Assignment 2",
    kind: "assignment",
    due_at: toIso("2026-11-28", "23:59"),
    weight: 40,
    status: "upcoming",
    notes: null,
    topic_ids: ["c", "q"],
  });
});

test("shows the server's validation message and keeps the dialog open", async () => {
  const { user } = renderTab([], () =>
    json(
      { detail: [{ loc: ["body", "weight"], msg: "Input should be less than or equal to 100" }] },
      422,
    ),
  );

  await user.click(await screen.findByRole("button", { name: "Add assessment" }));
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText("Title"), "Exam");
  await user.type(within(dialog).getByLabelText("Weight (%)"), "150");
  await user.click(within(dialog).getByRole("button", { name: "Add assessment" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "weight: Input should be less than or equal to 100",
  );
});

test("edits an assessment, prefilled, and replaces its topics", async () => {
  const { calls, user } = renderTab([anAssessment()]);

  await user.click(await screen.findByRole("button", { name: "Edit: Semester test 1" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit Semester test 1" });
  expect(within(dialog).getByLabelText("Date")).toHaveValue("2026-11-20");
  expect(within(dialog).getByLabelText("Time")).toHaveValue("09:00");
  expect(within(dialog).getByLabelText("Patterns")).toBeChecked();

  await user.click(within(dialog).getByLabelText("Patterns"));
  await user.click(within(dialog).getByLabelText("Queues"));
  await user.selectOptions(within(dialog).getByLabelText("Status"), "completed");
  await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(sent(calls, "PATCH")).toBeDefined());
  expect(sent(calls, "PATCH")).toMatchObject({
    path: "/assessments/a1",
    body: { topic_ids: ["q"], status: "completed", weight: 30 },
  });
});

test("deletes after confirming", async () => {
  const { calls, user } = renderTab([anAssessment()]);

  await user.click(await screen.findByRole("button", { name: "Delete: Semester test 1" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete “Semester test 1”?" });
  expect(dialog).toHaveTextContent("Tasks linked to it are kept");
  await user.click(within(dialog).getByRole("button", { name: "Delete assessment" }));

  await waitFor(() => expect(sent(calls, "DELETE")?.path).toBe("/assessments/a1"));
});
