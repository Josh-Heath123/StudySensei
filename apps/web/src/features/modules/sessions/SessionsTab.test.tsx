import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule, aSession, aTopic, roots } from "../fixtures";
import type { SessionRow } from "./api";

// Friday 13 November 2026, 10:00 local time.
const NOW = new Date(2026, 10, 13, 10, 0);
const MONDAY = new Date(2026, 10, 9);
const MIN = 60;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

const TREE = roots(aTopic("t1", "Layers"), aTopic("t2", "Quality attributes"));

const SUMMARY = {
  session_count: 3,
  active_seconds: 135 * MIN,
  week_start: MONDAY.toISOString(),
  week_active_seconds: 85 * MIN,
};

/** Stub the API. The list handler serves `sessions` a page at a time, by limit and offset. */
function api(sessions: SessionRow[], details: Record<string, unknown> = {}) {
  return mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => TREE,
    "GET /sessions/active": () => null,
    "GET /modules/:id/sessions/summary": () => SUMMARY,
    "GET /modules/:id/sessions": ({ query }) => {
      const limit = Number(query.get("limit"));
      const offset = Number(query.get("offset"));
      return {
        items: sessions.slice(offset, offset + limit),
        total: sessions.length,
        limit,
        offset,
      };
    },
    "GET /sessions/:id": ({ params }) => details[params.id!],
  });
}

const openTab = () => renderApp("/modules/m1?tab=sessions");

test("summarises measured study time this week and all time", async () => {
  const { fetchMock } = api([aSession()]);
  openTab();

  const summary = await screen.findByRole("region", { name: "Study time" });
  expect(within(summary).getByText("This week").nextSibling).toHaveTextContent("1 h 25 min");
  expect(within(summary).getByText("All time").nextSibling).toHaveTextContent("2 h 15 min");
  expect(within(summary).getByText("Sessions").nextSibling).toHaveTextContent("3");
  expect(
    screen.getByText(
      "Measured · active time from timer events, 3 sessions. This week starts Monday.",
    ),
  ).toBeInTheDocument();

  // "This week" is the student's own week: Monday 00:00 local time.
  const asked = fetchMock.mock.calls
    .map(([request]) => new URL(request.url))
    .find((url) => url.pathname.endsWith("/sessions/summary"));
  expect(asked?.searchParams.get("week_start")).toBe(MONDAY.toISOString());
});

test("lists sessions with the one in progress first, with a Resume button", async () => {
  api([
    aSession({
      id: "open",
      topic_id: "t2",
      state: "active",
      started_at: "2026-11-13T07:30:00Z",
      ended_at: null,
      // 20 min up to its last event, which was 10 min ago: 30 min so far.
      active_seconds: 20 * MIN,
      break_seconds: 0,
      last_event_at: new Date(NOW.getTime() - 10 * 60_000).toISOString(),
      focus_rating: null,
      reflected_at: null,
    }),
    aSession({
      id: "done",
      topic_id: "t1",
      focus_rating: 4,
      topic_ratings: [
        { topic_id: "t1", confidence: 3 },
        { topic_id: "t2", confidence: 5 },
      ],
    }),
    aSession({ id: "unreflected", started_at: "2026-11-10T08:00:00Z", focus_rating: null }),
  ]);
  openTab();

  const items = within(await screen.findByRole("list", { name: "Sessions" })).getAllByRole(
    "listitem",
  );
  expect(items).toHaveLength(3);

  const [open, done, unreflected] = items as [HTMLElement, HTMLElement, HTMLElement];
  expect(open).toHaveTextContent("In progress");
  expect(open).toHaveTextContent("Quality attributes");
  expect(open).toHaveTextContent("Active 30 min");
  expect(within(open).getByRole("link", { name: "Resume" })).toHaveAttribute("href", "/session");

  expect(done).toHaveTextContent("Layers");
  expect(done).toHaveTextContent("Active 50 min");
  expect(done).toHaveTextContent("Break 10 min");
  expect(done).toHaveTextContent("Focus 4/5");
  expect(done).toHaveTextContent("Layers 3/5");
  expect(done).toHaveTextContent("Quality attributes 5/5");
  expect(within(done).queryByRole("link", { name: "Resume" })).not.toBeInTheDocument();

  expect(unreflected).toHaveTextContent("Whole module");
  expect(unreflected).toHaveTextContent("No reflection");
});

test("opening a session shows its reflection and event timeline", async () => {
  const at = (h: number, m: number) => new Date(2026, 10, 12, h, m).toISOString();
  const session = aSession({
    topic_id: "t1",
    started_at: at(9, 0),
    covered_notes: "Layered style and its trade-offs",
    topic_ratings: [{ topic_id: "t1", confidence: 3 }],
  });
  api([session], {
    s1: {
      ...session,
      events: [
        { id: "e1", type: "start", occurred_at: at(9, 0) },
        { id: "e2", type: "pause", occurred_at: at(9, 20) },
        { id: "e3", type: "resume", occurred_at: at(9, 25) },
        { id: "e4", type: "break_start", occurred_at: at(9, 55) },
        { id: "e5", type: "break_end", occurred_at: at(10, 5) },
        { id: "e6", type: "end", occurred_at: at(10, 10) },
      ],
    },
  });
  openTab();
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /Layers/ }));

  const dialog = await screen.findByRole("dialog");
  const reflection = await within(dialog).findByRole("region", { name: "Reflection" });
  expect(reflection).toHaveTextContent("Focus4/5");
  expect(reflection).toHaveTextContent("Layered style and its trade-offs");
  expect(reflection).toHaveTextContent("LayersConfidence 3/5");
  expect(dialog).toHaveTextContent("Measured · from 6 timer events");

  const timeline = within(dialog).getByRole("list", { name: "Timeline" });
  expect(
    within(timeline)
      .getAllByRole("listitem")
      .map((li) => li.textContent),
  ).toEqual([
    "09:00Started",
    "09:20Paused",
    "09:25Resumed",
    "09:55Break started",
    "10:05Break ended",
    "10:10Ended",
  ]);
});

test("loads older sessions a page at a time", async () => {
  const sessions = Array.from({ length: 23 }, (_, i) =>
    aSession({ id: `s${i}`, started_at: new Date(Date.UTC(2026, 9, 30 - i, 8)).toISOString() }),
  );
  const { calls } = api(sessions);
  openTab();
  const user = userEvent.setup();

  const list = await screen.findByRole("list", { name: "Sessions" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(20);

  await user.click(screen.getByRole("button", { name: "Show older sessions" }));

  await vi.waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(23));
  expect(screen.queryByRole("button", { name: "Show older sessions" })).not.toBeInTheDocument();
  expect(calls.filter((c) => c.path === "/modules/m1/sessions")).toHaveLength(2);
});

test("with no sessions yet, says so", async () => {
  api([]);
  openTab();

  expect(await screen.findByText(/No sessions yet/)).toBeInTheDocument();
});
