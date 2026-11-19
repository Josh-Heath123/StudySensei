import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { onTestFinished, vi } from "vitest";

import { fakeSessionServer } from "@/test/fakeSessionServer";
import { renderApp } from "@/test/render";

import { aModule, aTopic, roots } from "../modules/fixtures";

const SEC = 1000;
const MIN = 60 * SEC;
// Friday 13 November 2026, 09:00 local time.
const T0 = new Date(2026, 10, 13, 9, 0);

const TREE = roots(
  aTopic("t1", "Architecture styles", [aTopic("t2", "Layers")]),
  aTopic("t3", "Quality attributes"),
);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0);
  // Testing Library's waitFor/findBy advance fake timers through a `jest` global.
  vi.stubGlobal("jest", { advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms) });
});

afterEach(() => {
  vi.useRealTimers();
});

function serve() {
  return fakeSessionServer({
    "GET /health": () => ({ status: "ok", api: "ok", database: "ok" }),
    "GET /modules": () => [aModule(), aModule({ id: "m2", code: "COS301", name: "Other" })],
    "GET /modules/:id": ({ params }) => aModule({ id: params.id! }),
    "GET /modules/:id/topics": () => TREE,
    "GET /assessments": () => [],
    "GET /tasks": () => [],
  });
}

const setupUser = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

/** Let `ms` pass with the page open (the redraw interval fires every second). */
const pass = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

const timer = () => screen.getByRole("timer");
const eyebrow = () => timer().previousElementSibling;

async function startFromToday(user: ReturnType<typeof setupUser>) {
  const view = renderApp("/");
  const start = await screen.findByRole("button", { name: "Start session" });
  await waitFor(() => expect(start).toBeEnabled());
  await user.click(start);
  const dialog = await screen.findByRole("dialog", { name: "Start a study session" });
  await user.selectOptions(within(dialog).getByLabelText("Module"), "m1");
  const topic = within(dialog).getByLabelText("Topic (optional)");
  await waitFor(() => expect(topic).toBeEnabled());
  await user.selectOptions(topic, "t2");
  await user.click(within(dialog).getByRole("button", { name: "Start" }));
  await screen.findByRole("timer");
  return view;
}

test("start → pause → resume → break → end → reflect → summary", async () => {
  const server = serve();
  const user = setupUser();

  await startFromToday(user);
  expect(screen.getByRole("heading", { level: 1, name: "Layers" })).toBeInTheDocument();
  expect(await screen.findByText("COS330")).toBeInTheDocument();
  expect(timer()).toHaveTextContent("50:00");
  expect(eyebrow()).toHaveTextContent("Focus");
  expect(screen.getByRole("complementary", { name: "Tutor" })).toBeInTheDocument();
  expect(
    screen.getByText(/Open this module's slides and notes, search them, and jump to any page/),
  ).toBeInTheDocument();
  // After the timer (#34 item 12): the Materials link, then the tutor.
  const timerSection = screen.getByRole("region", { name: "Timer" });
  const materials = screen.getByRole("link", { name: "Open module" });
  expect(materials).toHaveAttribute("href", "/modules/m1");
  // The tutor sits beside the timer on a desktop (after it in reading order), never inside.
  const tutor = screen.getByRole("complementary", { name: "Tutor" });
  for (const below of [materials, tutor]) {
    expect(
      timerSection.compareDocumentPosition(below) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(timerSection.contains(below)).toBe(false);
  }

  await pass(10 * MIN);
  expect(timer()).toHaveTextContent("40:00");
  expect(document.title).toBe("40:00 focus · StudySensei");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20");

  await user.click(screen.getByRole("button", { name: "Pause" }));
  expect(eyebrow()).toHaveTextContent("Paused");
  await pass(5 * MIN);
  expect(timer()).toHaveTextContent("40:00");
  expect(document.title).toBe("Paused · 40:00 · StudySensei");

  await user.click(screen.getByRole("button", { name: "Resume" }));
  expect(screen.queryByText(/Break due\./)).not.toBeInTheDocument();
  await pass(40 * MIN);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Break due. You've focused for 50 min. Take a break when you reach a good stopping point.",
  );
  expect(eyebrow()).toHaveTextContent("Focus · break due");

  await user.click(screen.getByRole("button", { name: "Break now" }));
  expect(eyebrow()).toHaveTextContent("Break");
  expect(timer()).toHaveTextContent("10:00");
  await pass(8 * MIN);
  expect(timer()).toHaveTextContent("02:00");

  await user.click(screen.getByRole("button", { name: "End break" }));
  await pass(1 * MIN);
  await user.click(screen.getByRole("button", { name: "End session" }));

  // Reflection
  expect(
    await screen.findByRole("heading", { level: 1, name: "How did it go?" }),
  ).toBeInTheDocument();
  expect(document.title).not.toContain("focus");
  const focus = screen.getByRole("group", { name: "How focused were you?" });
  await user.click(within(focus).getByRole("radio", { name: "4" }));
  await user.type(screen.getByLabelText("What I covered"), "Layered style and its trade-offs");
  // The session's topic starts ticked.
  expect(screen.getByRole("checkbox", { name: "Layers" })).toBeChecked();
  await user.click(screen.getByRole("checkbox", { name: "Quality attributes" }));
  await user.click(screen.getByRole("button", { name: "Save reflection" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Rate your confidence for each topic you ticked.",
  );
  const layers = screen.getByRole("group", { name: "Confidence in Layers" });
  await user.click(within(layers).getByRole("radio", { name: "3" }));
  const quality = screen.getByRole("group", { name: "Confidence in Quality attributes" });
  await user.click(within(quality).getByRole("radio", { name: "5" }));
  await user.click(screen.getByRole("button", { name: "Save reflection" }));

  // Summary
  expect(
    await screen.findByRole("heading", { level: 1, name: "Session summary" }),
  ).toBeInTheDocument();
  const active = screen.getByText("Active time").parentElement!;
  expect(active).toHaveTextContent("51 min");
  expect(active).toHaveTextContent("Measured · from 6 timer events");
  expect(screen.getByText("Break time").parentElement).toHaveTextContent("8 min");
  expect(screen.getByRole("link", { name: "Back to Today" })).toHaveAttribute("href", "/");

  const session = server.only();
  expect(session).toMatchObject({ module_id: "m1", topic_id: "t2" });
  expect(session.events.map((e) => e.type)).toEqual([
    "start",
    "pause",
    "resume",
    "break_start",
    "break_end",
    "end",
  ]);
  expect(session.reflection).toEqual({
    focus_rating: 4,
    covered_notes: "Layered style and its trade-offs",
    topic_ratings: [
      { topic_id: "t2", confidence: 3 },
      { topic_id: "t3", confidence: 5 },
    ],
  });
});

test("a reload lands back in the running session", async () => {
  serve();
  const user = setupUser();
  const first = await startFromToday(user);
  await pass(10 * MIN);
  expect(timer()).toHaveTextContent("40:00");

  // Reload: a new page load with the same localStorage and server.
  first.unmount();
  await pass(5 * SEC);
  renderApp("/session");

  expect(await screen.findByRole("timer")).toHaveTextContent("39:55");
  expect(screen.getByRole("heading", { level: 1, name: "Layers" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("Start session returns to the open session instead of starting another", async () => {
  serve();
  const user = setupUser();
  await startFromToday(user);

  await user.click(screen.getByRole("link", { name: "Today" }));

  const back = await screen.findByRole("link", { name: "Return to session" });
  expect(back).toHaveAttribute("href", "/session");
  expect(screen.queryByRole("button", { name: "Start session" })).not.toBeInTheDocument();
});

test("a module's page starts a session for that module", async () => {
  const server = serve();
  const user = setupUser();
  renderApp("/modules/m2");

  const start = await screen.findByRole("button", { name: "Start session" });
  await waitFor(() => expect(start).toBeEnabled());
  await user.click(start);
  const dialog = await screen.findByRole("dialog", { name: "Start a study session" });
  expect(within(dialog).queryByLabelText("Module")).not.toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Start" }));

  expect(await screen.findByRole("heading", { level: 1, name: "Whole module" })).toBeVisible();
  await waitFor(() => expect(server.sessions.size).toBe(1));
  expect(server.only()).toMatchObject({ module_id: "m2", topic_id: null });
});

test("after time away, asks first; pausing stops the clock when you left", async () => {
  const server = serve();
  const user = setupUser();
  await startFromToday(user);
  await pass(10 * MIN);

  act(() => vi.setSystemTime(Date.now() + 5 * MIN)); // the laptop slept: no ticks
  await pass(1 * SEC);

  const dialog = screen.getByRole("dialog", { name: "Were you away?" });
  expect(dialog).toHaveTextContent("You were away for 5 min.");
  expect(within(dialog).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.getByRole("dialog", { name: "Were you away?" })).toBeInTheDocument();

  await user.click(within(dialog).getByRole("button", { name: "Pause from when I left" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(eyebrow()).toHaveTextContent("Paused");
  expect(timer()).toHaveTextContent("40:00");
  expect(server.only().events.map((e) => e.type)).toEqual(["start", "pause"]);
});

test("changes made offline are sent when the browser is back online", async () => {
  const server = serve();
  const user = setupUser();
  await startFromToday(user);
  await pass(1 * MIN);

  server.setMode("offline");
  await user.click(screen.getByRole("button", { name: "Pause" }));
  expect(await screen.findByText(/Your changes are saved on this device/)).toBeInTheDocument();
  expect(server.only().events.map((e) => e.type)).toEqual(["start"]);

  server.setMode("online");
  await act(async () => {
    fireEvent(window, new Event("online"));
  });

  await waitFor(() => expect(server.only().events.map((e) => e.type)).toEqual(["start", "pause"]));
  await waitFor(() =>
    expect(screen.queryByText(/Your changes are saved on this device/)).not.toBeInTheDocument(),
  );
});

test("queued changes are sent when the tab becomes visible again", async () => {
  const server = serve();
  const user = setupUser();
  await startFromToday(user);

  server.setMode("offline");
  await user.click(screen.getByRole("button", { name: "Break now" }));
  expect(await screen.findByText(/Your changes are saved on this device/)).toBeInTheDocument();
  server.setMode("online");
  // jsdom reports "prerender"; the tab is now in front.
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  onTestFinished(() => void Reflect.deleteProperty(document, "visibilityState"));
  await act(async () => {
    fireEvent(document, new Event("visibilitychange"));
  });

  await waitFor(() =>
    expect(server.only().events.map((e) => e.type)).toEqual(["start", "break_start"]),
  );
});

test("keeps retrying queued changes while the page stays open", async () => {
  const server = serve();
  const user = setupUser();
  await startFromToday(user);

  server.setMode("offline");
  await user.click(screen.getByRole("button", { name: "Pause" }));
  expect(await screen.findByText(/Your changes are saved on this device/)).toBeInTheDocument();
  server.setMode("online");

  await pass(30 * SEC);

  expect(server.only().events.map((e) => e.type)).toEqual(["start", "pause"]);
});
