import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { json, mockApi, noContent, type ApiCall } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { Plan } from "./api";
import { aBlock, aPlan, UTC_SETTINGS } from "./fixtures";
import { PX_PER_MINUTE } from "./WeekGrid";

// Friday 13 November 2026, 10:00 UTC: the week is Mon 9 – Sun 15 Nov.
const NOW = new Date("2026-11-13T10:00:00Z");

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** 18:00-21:00 every evening of the week, plus Saturday morning 09:00-12:00. */
function availability(unavailable: string[] = []) {
  const days = ["09", "10", "11", "12", "13", "14", "15"].map((d) => {
    const date = `2026-11-${d}`;
    const off = unavailable.includes(date);
    const intervals = off
      ? []
      : [
          ...(d === "14"
            ? [{ start: `${date}T09:00:00Z`, end: `${date}T12:00:00Z`, minutes: 180 }]
            : []),
          { start: `${date}T18:00:00Z`, end: `${date}T21:00:00Z`, minutes: 180 },
        ];
    return {
      date,
      weekday: 0,
      source: off ? "unavailable" : "rules",
      intervals,
      free_minutes: 180,
      available_minutes: 180,
    };
  });
  return {
    timezone: "UTC",
    daily_study_cap_minutes: 180,
    days,
    total_free_minutes: 0,
    total_available_minutes: 0,
    weekly_minutes_from_rules: 0,
  };
}

function renderPlan(
  plan: () => Plan,
  options: {
    exceptions?: unknown[];
    unavailable?: string[];
    reply?: (call: ApiCall) => unknown;
  } = {},
) {
  const api = mockApi({
    "GET /sessions/active": () => null,
    "GET /planning/settings": () => UTC_SETTINGS,
    "GET /plan": plan,
    "GET /availability": () => availability(options.unavailable),
    "GET /availability/exceptions": () => options.exceptions ?? [],
    "GET /availability/rules": () => [{ id: "r1", weekday: 0, start: "18:00", end: "21:00" }],
    "POST /plan/blocks/:id/skip": (call) => options.reply?.(call) ?? aPlan(),
    "POST /plan/blocks/:id/move": (call) => options.reply?.(call) ?? aPlan(),
    "POST /availability/exceptions": (call) => options.reply?.(call) ?? json({}, 201),
    "PATCH /availability/exceptions/:id": (call) => options.reply?.(call) ?? {},
    "DELETE /availability/exceptions/:id": () => noContent(),
  });
  renderApp("/plan");
  return { ...api, user: userEvent.setup() };
}

const posts = (calls: ApiCall[], path: string) =>
  calls.filter((c) => c.method !== "GET" && c.path === path);

test("the header has the version summary, the overall line and its status, and Details", async () => {
  renderPlan(() => aPlan([aBlock()]));

  expect(await screen.findByRole("heading", { level: 1, name: "Plan" })).toBeInTheDocument();
  expect(
    await screen.findByText(
      "Updated 07:43 · You skipped Ch1 Overview (Thu 12 Nov, 18:00): its time is placed again.",
    ),
  ).toBeInTheDocument();
  const feasibility = screen.getByRole("region", { name: "Feasibility" });
  expect(feasibility).toHaveTextContent("FitsYou need 4 h before 20 Nov and have 21 h.");
  expect(within(feasibility).getByText("Details")).toBeInTheDocument();
  expect(feasibility).toHaveTextContent("COS330 Exam (20 Nov): needs 4 h");
});

test("blocks sit in their day's column at their local time; free windows are bands", async () => {
  renderPlan(() =>
    aPlan([
      aBlock({ id: "fri", start: "2026-11-13T18:00:00Z", end: "2026-11-13T18:50:00Z" }),
      aBlock({ id: "sat", start: "2026-11-14T09:30:00Z", end: "2026-11-14T10:20:00Z" }),
    ]),
  );

  const grid = await screen.findByTestId("week-grid");
  const friday = grid.querySelector('[data-date="2026-11-13"]')!;
  const saturday = grid.querySelector('[data-date="2026-11-14"]')!;
  const fri = within(friday as HTMLElement).getByRole("button", { name: /18:00 to 18:50/ });
  const sat = within(saturday as HTMLElement).getByRole("button", { name: /09:30 to 10:20/ });
  // The hour rows start at the week's earliest window (09:00) and end at its latest (21:00).
  expect(fri.parentElement!.style.top).toBe(`${(18 - 9) * 60 * PX_PER_MINUTE}px`);
  expect(sat.parentElement!.style.top).toBe(`${30 * PX_PER_MINUTE}px`);
  expect(grid).toHaveTextContent("09:00");
  expect(grid).toHaveTextContent("21:00");
  expect(grid).not.toHaveTextContent("00:00");
  expect(saturday.querySelectorAll("[data-free-band]")).toHaveLength(2);
});

test("statuses: done with measured minutes, skipped, missed, and now", async () => {
  vi.setSystemTime(new Date("2026-11-13T18:10:00Z"));
  renderPlan(() =>
    aPlan([
      aBlock({
        id: "done",
        start: "2026-11-11T18:00:00Z",
        end: "2026-11-11T18:50:00Z",
        status: "done",
        session_minutes: 48,
      }),
      aBlock({
        id: "skip",
        start: "2026-11-12T18:00:00Z",
        end: "2026-11-12T18:50:00Z",
        status: "skipped",
      }),
      aBlock({
        id: "miss",
        start: "2026-11-10T18:00:00Z",
        end: "2026-11-10T18:50:00Z",
        status: "missed",
      }),
      aBlock({ id: "now" }),
    ]),
  );

  const grid = await screen.findByTestId("week-grid");
  const card = (id: string) => grid.querySelector(`[data-block-id="${id}"]`)!;
  expect(card("done")).toHaveTextContent("48 min (measured)");
  expect(card("skip")).toHaveTextContent("Skipped");
  expect(card("skip").querySelector(".line-through")).not.toBeNull();
  expect(card("miss")).toHaveTextContent("Missed");
  expect(card("now")).toHaveTextContent("Now");
  expect(card("now")).toHaveAttribute("data-status", "now");
});

test("the popover's buttons follow the block's action flags", async () => {
  const { user } = renderPlan(() =>
    aPlan([
      aBlock({ id: "all", pinned: true, fixed: true }),
      aBlock({
        id: "none",
        start: "2026-11-14T18:00:00Z",
        end: "2026-11-14T18:50:00Z",
        fixed: true,
        actions: { start: false, skip: false, move: false },
      }),
    ]),
  );
  const grid = await screen.findByTestId("week-grid");

  await user.click(grid.querySelector('[data-block-id="all"]')!);
  let popover = await screen.findByRole("dialog", { name: "Ch2 Cryptography" });
  expect(popover).toHaveTextContent("Why≈ 4 h estimated from 40 slides");
  expect(popover).toHaveTextContent("HowQuiz yourself first");
  expect(popover).toHaveTextContent("Moved by you.");
  expect(
    within(popover)
      .getAllByRole("button")
      .map((b) => b.textContent?.trim()),
  ).toEqual(["Start session", "Move…", "Skip"]);
  await user.keyboard("{Escape}");

  await user.click(grid.querySelector('[data-block-id="none"]')!);
  popover = await screen.findByRole("dialog", { name: "Ch2 Cryptography" });
  expect(popover).toHaveTextContent("Kept for the next 24 h.");
  expect(within(popover).queryAllByRole("button")).toEqual([]);
});

test("skip asks first, then posts", async () => {
  const { user, calls } = renderPlan(() => aPlan([aBlock()]));
  const grid = await screen.findByTestId("week-grid");
  await user.click(grid.querySelector('[data-block-id="b1"]')!);
  const popover = await screen.findByRole("dialog", { name: "Ch2 Cryptography" });
  await user.click(within(popover).getByRole("button", { name: "Skip" }));
  const confirm = await screen.findByRole("dialog", { name: "Skip this block?" });
  expect(posts(calls, "/plan/blocks/b1/skip")).toHaveLength(0);
  await user.click(within(confirm).getByRole("button", { name: "Skip" }));
  await waitFor(() => expect(posts(calls, "/plan/blocks/b1/skip")).toHaveLength(1));
});

test("Move… offers the week's free 5-minute times and shows the server's sentence", async () => {
  const { user, calls } = renderPlan(() => aPlan([aBlock()]), {
    reply: (call) =>
      call.path.endsWith("/move")
        ? json({ detail: "Leave 10 minutes between blocks." }, 422)
        : undefined,
  });
  const grid = await screen.findByTestId("week-grid");
  await user.click(grid.querySelector('[data-block-id="b1"]')!);
  await user.click(await screen.findByRole("button", { name: "Move…" }));
  const dialog = await screen.findByRole("dialog", { name: "Move Ch2 Cryptography" });

  await user.selectOptions(within(dialog).getByLabelText("Day"), "2026-11-14");
  const times = within(dialog)
    .getAllByRole("option")
    .filter((o) => o.closest("select")?.id === "move-time")
    .map((o) => o.textContent);
  // Saturday: 09:00-11:10 in the morning window, then 18:00-20:10 in the evening one.
  expect(times[0]).toBe("09:00");
  expect(times).toContain("11:10");
  expect(times).not.toContain("11:15");
  expect(times.at(-1)).toBe("20:10");
  await user.selectOptions(within(dialog).getByLabelText("Start"), "09:30");
  await user.click(within(dialog).getByRole("button", { name: "Move" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Leave 10 minutes between blocks.",
  );
  expect(posts(calls, "/plan/blocks/b1/move")[0]!.body).toEqual({
    start: "2026-11-14T09:30:00.000Z",
  });
});

test("mark a day unavailable: a new exception", async () => {
  const { user, calls } = renderPlan(() => aPlan([]));
  await user.click(await screen.findByRole("button", { name: "Wed 11 Nov: options" }));
  await user.click(await screen.findByRole("menuitem", { name: "Mark unavailable" }));
  await waitFor(() => expect(posts(calls, "/availability/exceptions")).toHaveLength(1));
  expect(posts(calls, "/availability/exceptions")[0]!.body).toEqual({
    date: "2026-11-11",
    unavailable: true,
    windows: [],
  });
});

test("mark a day with custom hours unavailable: replaces them after a confirmation", async () => {
  const custom = {
    id: "e1",
    date: "2026-11-11",
    unavailable: false,
    windows: [{ start: "10:00", end: "12:00" }],
    note: null,
  };
  const { user, calls } = renderPlan(() => aPlan([]), { exceptions: [custom] });
  await user.click(await screen.findByRole("button", { name: "Wed 11 Nov: options" }));
  await user.click(await screen.findByRole("menuitem", { name: "Mark unavailable" }));
  const confirm = await screen.findByRole("dialog", { name: "Mark Wed 11 Nov unavailable?" });
  expect(confirm).toHaveTextContent("This replaces the custom hours you set for that day.");
  await user.click(within(confirm).getByRole("button", { name: "Mark unavailable" }));
  await waitFor(() => expect(posts(calls, "/availability/exceptions/e1")).toHaveLength(1));
  expect(posts(calls, "/availability/exceptions/e1")[0]!.body).toEqual({
    unavailable: true,
    windows: [],
  });
});

test("an unavailable day says so, and can be made available again", async () => {
  const off = { id: "e2", date: "2026-11-12", unavailable: true, windows: [], note: null };
  const { user, calls } = renderPlan(() => aPlan([]), {
    exceptions: [off],
    unavailable: ["2026-11-12"],
  });
  const grid = await screen.findByTestId("week-grid");
  expect(await within(grid).findByText("Unavailable")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Thu 12 Nov: options" }));
  await user.click(await screen.findByRole("menuitem", { name: "Make available again" }));
  const confirm = await screen.findByRole("dialog", { name: "Make Thu 12 Nov available again?" });
  expect(confirm).toHaveTextContent("The day goes back to your weekly hours.");
  await user.click(within(confirm).getByRole("button", { name: "Make available" }));
  await waitFor(() =>
    expect(calls.filter((c) => c.method === "DELETE").map((c) => c.path)).toEqual([
      "/availability/exceptions/e2",
    ]),
  );
});

test("while a re-plan is pending it says so and polls until it's done", async () => {
  let reads = 0;
  renderPlan(() => {
    reads += 1;
    return aPlan([aBlock()], { replan_pending: reads < 2 });
  });
  expect(await screen.findByText("Updating your plan…")).toBeInTheDocument();
  await waitFor(() => expect(reads).toBeGreaterThanOrEqual(2), { timeout: 4000 });
  await waitFor(() => expect(screen.queryByText("Updating your plan…")).not.toBeInTheDocument());
});

test("below 1024 px the week is an agenda by day, with no grid", async () => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("640"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  renderPlan(() =>
    aPlan([
      aBlock(),
      aBlock({ id: "b2", start: "2026-11-14T09:30:00Z", end: "2026-11-14T10:20:00Z" }),
    ]),
  );
  const agenda = await screen.findByTestId("agenda");
  expect(screen.queryByTestId("week-grid")).not.toBeInTheDocument();
  const days = within(agenda)
    .getAllByRole("listitem")
    .filter((li) => li.parentElement === agenda);
  expect(days).toHaveLength(7);
  expect(days[4]).toHaveTextContent("Fri 13 NovTodayFree 18:00–21:00");
  expect(days[4]).toHaveTextContent("Ch2 Cryptography18:00–18:50");
  expect(days[5]).toHaveTextContent("Free 09:00–12:00, 18:00–21:00");
  expect(days[0]).toHaveTextContent("Nothing planned.");
});

test("with no study time, the plan points to Settings", async () => {
  mockApi({
    "GET /sessions/active": () => null,
    "GET /planning/settings": () => UTC_SETTINGS,
    "GET /plan": () => aPlan([]),
    "GET /availability": () => availability(),
    "GET /availability/exceptions": () => [],
    "GET /availability/rules": () => [],
  });
  renderApp("/plan");
  expect(await screen.findByText("Add your study time")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Settings → Study time" })).toHaveAttribute(
    "href",
    "/settings",
  );
});
