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
import type { PlanBlock } from "../plan/api";
import { aBlock, aPlan, UTC_SETTINGS } from "../plan/fixtures";
import type { QueueCounts } from "../practice/api";
import { aQueue } from "../practice/fixtures";

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
  data: {
    modules?: Module[];
    assessments?: Assessment[];
    tasks?: Task[];
    next?: PlanBlock | null;
    day?: PlanBlock[];
    queue?: Partial<QueueCounts>;
  },
  reply?: (call: ApiCall) => unknown,
) {
  const api = mockApi({
    "GET /health": () => HEALTHY,
    "GET /sessions/active": () => null,
    "GET /modules": () => data.modules ?? [aModule()],
    "GET /assessments": () => data.assessments ?? [],
    "GET /tasks": () => data.tasks ?? [],
    "PATCH /tasks/:id": (call) => reply?.(call) ?? {},
    "PATCH /assessments/:id": (call) => reply?.(call) ?? {},
    "GET /planning/settings": () => UTC_SETTINGS,
    "GET /plan/next": () => data.next ?? null,
    "GET /plan": () => aPlan(data.day ?? []),
    "POST /plan/blocks/:id/skip": () => aPlan(),
    "GET /practice/queue": () => aQueue([], data.queue ?? {}),
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
    "GET /sessions/active": () => null,
    "GET /modules": () => [aModule()],
    "GET /assessments": () => [],
    "GET /tasks": () => new Response(JSON.stringify({ detail: "Boom" }), { status: 500 }),
    "GET /practice/queue": () => aQueue(),
  });
  renderApp("/");

  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load deadlines");
});

test("the header shows the date and countdowns to the next real assessments", async () => {
  renderToday({
    modules: [aModule(), aModule({ id: "m2", code: "COS301", colour: "#5EE0B0" })],
    assessments: [
      anAssessment({ id: "late", title: "Missed test", due_at: toIso("2026-11-10", "09:00") }),
      anAssessment({
        id: "a2",
        title: "Assignment 2",
        module_id: "m2",
        due_at: toIso("2026-11-25", "23:59"),
      }),
      anAssessment({ id: "a1", title: "Semester test", due_at: toIso("2026-11-14", "09:00") }),
    ],
  });

  expect(screen.getByRole("heading", { level: 1, name: "13 November" })).toBeInTheDocument();
  expect(screen.getByText("Friday")).toBeInTheDocument();
  const tiles = within(await screen.findByRole("list", { name: "Countdowns" })).getAllByRole(
    "listitem",
  );
  expect(tiles.map((tile) => tile.textContent)).toEqual([
    expect.stringContaining("1day to Semester testCOS330"),
    expect.stringContaining("12days to Assignment 2COS301"),
  ]);
  // The nearest deadline is marked; overdue ones stay in the list instead.
  expect(tiles[0]).toHaveAttribute("data-nearest", "true");
  expect(tiles[1]).toHaveAttribute("data-nearest", "false");
});

test("with no plan, Next up offers an unplanned session and links to what a plan needs", async () => {
  renderToday({});

  const nextUp = await screen.findByRole("region", { name: "Nothing planned yet" });
  expect(within(nextUp).getByRole("link", { name: "Add study time" })).toHaveAttribute(
    "href",
    "/settings",
  );
  expect(within(nextUp).getByRole("link", { name: "an assessment" })).toHaveAttribute(
    "href",
    "/modules",
  );
  expect(
    within(nextUp)
      .getAllByRole("button")
      .map((b) => b.textContent?.trim()),
  ).toEqual(["Start session"]);
  const day = screen.getByRole("region", { name: "Your day" });
  expect(await within(day).findByText("Nothing planned today.")).toBeInTheDocument();
  expect(within(day).queryByText("08:00")).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Countdowns" })).not.toBeInTheDocument();
});

test("Next up names the plan's next block, with its method, reason and actions", async () => {
  const block = aBlock();
  const { calls } = renderToday({ next: block });

  const nextUp = await screen.findByRole("region", { name: "Ch2 Cryptography" });
  expect(nextUp).toHaveTextContent("Today, 18:00 · 50 min · COS330 Exam");
  expect(nextUp).toHaveTextContent(block.method_text);
  expect(nextUp).toHaveTextContent(`Why: ${block.reason_text}`);
  expect(
    within(nextUp)
      .getAllByRole("button")
      .map((b) => b.textContent?.trim()),
  ).toEqual(["Start session", "Skip"]);

  // Skip asks first.
  const user = userEvent.setup();
  await user.click(within(nextUp).getByRole("button", { name: "Skip" }));
  const confirm = await screen.findByRole("dialog", { name: "Skip this block?" });
  await user.click(within(confirm).getByRole("button", { name: "Skip" }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === "POST" && c.path === "/plan/blocks/b1/skip")).toBe(true),
  );
});

test("a block in progress says Now, and only the actions the server allows show", async () => {
  const start = new Date(NOW.getTime() - 10 * 60_000).toISOString();
  const end = new Date(NOW.getTime() + 40 * 60_000).toISOString();
  renderToday({ next: aBlock({ start, end, actions: { start: false, skip: true, move: false } }) });

  const nextUp = await screen.findByRole("region", { name: "Ch2 Cryptography" });
  expect(nextUp).toHaveTextContent("Now · 50 min · COS330 Exam");
  expect(
    within(nextUp)
      .getAllByRole("button")
      .map((b) => b.textContent?.trim()),
  ).toEqual(["Skip"]);
});

test("Your day lists today's blocks with their status", async () => {
  renderToday({
    day: [
      aBlock({
        id: "d1",
        start: "2026-11-13T06:00:00Z",
        end: "2026-11-13T06:50:00Z",
        status: "done",
        session_minutes: 48,
        actions: { start: false, skip: false, move: false },
      }),
      aBlock({
        id: "s1",
        start: "2026-11-13T07:00:00Z",
        end: "2026-11-13T07:50:00Z",
        status: "skipped",
      }),
      aBlock({
        id: "p1",
        topic_id: null,
        topic_name: null,
        kind: "review",
        method: "mixed_review",
      }),
    ],
  });

  const day = await screen.findByRole("region", { name: "Your day" });
  const items = await within(day).findAllByRole("listitem");
  expect(items.map((i) => i.textContent)).toEqual([
    "06:00–06:50Ch2 CryptographyPractice48 min (measured)",
    "07:00–07:50Ch2 CryptographyPracticeSkipped",
    "18:00–18:50Final review · COS330 ExamMixed review",
  ]);
  expect(within(day).getByRole("link", { name: "Week" })).toHaveAttribute("href", "/plan");
});

test("the Reviews card: what's due and Start review", async () => {
  renderToday({ queue: { due_now: 4, new_today_left: 12, new_total: 30 } });
  const card = (await screen.findByText("Reviews")).closest("[data-slot=card]") as HTMLElement;
  expect(await within(card).findByText("4 due now · 12 new today")).toBeVisible();
  expect(within(card).getByRole("link", { name: "Start review" })).toHaveAttribute(
    "href",
    "/practice/review",
  );
});

test("with nothing due, the Reviews card says when the next review is", async () => {
  // NOW is 10:00 local; three hours on.
  const next = new Date(NOW.getTime() + 3 * 3_600_000).toISOString();
  renderToday({ queue: { next_due_at: next } });
  expect(await screen.findByText("Next review in 3 h.")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Start review" })).not.toBeInTheDocument();
  // Practice is still one click away when nothing is due.
  expect(screen.getByRole("link", { name: "Open practice" })).toHaveAttribute("href", "/practice");
});

test("with nothing scheduled, the Reviews card still opens practice", async () => {
  renderToday({ queue: { next_due_at: null } });
  expect(await screen.findByText(/Nothing to review yet/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Open practice" })).toHaveAttribute("href", "/practice");
});
