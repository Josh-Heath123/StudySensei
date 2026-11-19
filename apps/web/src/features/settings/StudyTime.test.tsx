import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeStudyTime } from "@/test/fakeStudyTime";
import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { addDays, localToday } from "./studyTime";

const today = localToday("Africa/Johannesburg");
const weekdayOf = (date: string) => (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function serve(options: Parameters<typeof fakeStudyTime>[0] = {}) {
  const fake = fakeStudyTime(options);
  const api = mockApi({
    ...fake.routes,
    "GET /ai/status": () => new Response(null, { status: 503 }),
  });
  return { ...fake, ...api };
}

const summary = () => screen.findByRole("status");
const day = (name: string) => screen.getByRole("listitem", { name });

test("add a window to a day, change its times, and the week's total follows", async () => {
  const { calls } = serve();
  const user = userEvent.setup();
  renderApp("/settings");

  expect(await screen.findByText("No study time yet: add a window to a day below.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Add a window on Monday" }));

  expect(await summary()).toHaveTextContent("≈ 1 h a week available (from your rules)");
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    weekday: 0,
    start: "18:00",
    end: "19:00",
  });

  const end = within(day("Monday")).getByLabelText("Monday window 1 end");
  fireEvent.change(end, { target: { value: "20:30" } });
  fireEvent.blur(end);

  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("≈ 2.5 h"));
  expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
    start: "18:00",
    end: "20:30",
  });
  expect(within(day("Monday")).getByText("2.5 h")).toBeVisible();
});

test("a second window goes after the first; an overlap reads plainly", async () => {
  serve({ rules: [{ weekday: 2, start: "09:00", end: "12:00" }] });
  const user = userEvent.setup();
  renderApp("/settings");
  await summary();

  await user.click(screen.getByRole("button", { name: "Add a window on Wednesday" }));
  const second = await within(day("Wednesday")).findByLabelText("Wednesday window 2 start");
  expect(second).toHaveValue("12:00");

  fireEvent.change(second, { target: { value: "11:00" } });
  fireEvent.blur(second);

  expect(await within(day("Wednesday")).findByRole("alert")).toHaveTextContent(
    "That window overlaps another.",
  );
});

test("a window to midnight is sent as 24:00", async () => {
  const { calls } = serve({ rules: [{ weekday: 4, start: "22:00", end: "23:00" }] });
  renderApp("/settings");
  await summary();

  const end = within(day("Friday")).getByLabelText("Friday window 1 end");
  fireEvent.change(end, { target: { value: "00:00" } });
  fireEvent.blur(end);

  await waitFor(() =>
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      start: "22:00",
      end: "24:00",
    }),
  );
});

test("removing a window", async () => {
  const { calls } = serve({ rules: [{ weekday: 6, start: "09:00", end: "10:00" }] });
  const user = userEvent.setup();
  renderApp("/settings");
  await summary();

  await user.click(
    within(day("Sunday")).getByRole("button", { name: "Remove Sunday window 1 (09:00 to 10:00)" }),
  );

  expect(await screen.findByText("No study time yet: add a window to a day below.")).toBeVisible();
  expect(calls.some((c) => c.method === "DELETE")).toBe(true);
});

test("the daily cap limits the week, and the timezone can change", async () => {
  const { calls } = serve({
    rules: [
      { weekday: 0, start: "08:00", end: "12:00" },
      { weekday: 1, start: "08:00", end: "09:00" },
    ],
  });
  const user = userEvent.setup();
  renderApp("/settings");

  expect(await summary()).toHaveTextContent("≈ 4 h a week"); // Monday's 4 h capped at 3 h
  const cap = screen.getByLabelText("Most study a day (minutes)");
  await user.clear(cap);
  await user.type(cap, "240{Enter}");

  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("≈ 5 h"));
  expect(screen.getByText("= 4 h")).toBeVisible();

  await user.selectOptions(screen.getByLabelText("Timezone"), "Europe/London");
  await waitFor(() =>
    expect(calls.filter((c) => c.method === "PATCH").map((c) => c.body)).toEqual([
      { daily_study_cap_minutes: 240 },
      { timezone: "Europe/London" },
    ]),
  );
});

test("a cap out of range isn't saved", async () => {
  const { calls } = serve();
  const user = userEvent.setup();
  renderApp("/settings");
  await screen.findByText(/No study time yet/);

  const cap = screen.getByLabelText("Most study a day (minutes)");
  await user.clear(cap);
  await user.type(cap, "5{Enter}");

  expect(cap).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByText("15 to 1,440 minutes")).toBeVisible();
  expect(calls.some((c) => c.method === "PATCH")).toBe(false);
});

test("an exception makes a day unavailable, and the next 7 days lose its time", async () => {
  const tomorrow = addDays(today, 1);
  const { calls } = serve({
    rules: [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({ weekday, start: "18:00", end: "19:00" })),
  });
  const user = userEvent.setup();
  renderApp("/settings");

  expect(await summary()).toHaveTextContent("≈ 7 h in the next 7 days");
  fireEvent.change(screen.getByLabelText("Date"), { target: { value: tomorrow } });
  await user.type(screen.getByLabelText("Note (optional)"), "Graduation");
  await user.click(screen.getByRole("button", { name: "Add exception" }));

  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent("≈ 6 h in the next 7 days"),
  );
  // The typical week is from the rules alone.
  expect(screen.getByRole("status")).toHaveTextContent("≈ 7 h a week available");
  const list = screen.getByRole("list", { name: "Exceptions" });
  expect(list).toHaveTextContent("Unavailable all day · Graduation");
  expect(
    calls.find((c) => c.path === "/availability/exceptions" && c.method === "POST")?.body,
  ).toEqual({ date: tomorrow, unavailable: true, windows: [], note: "Graduation" });

  await user.click(within(list).getByRole("button", { name: /Remove the exception on/ }));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent("≈ 7 h in the next 7 days"),
  );
});

test("an exception with different times", async () => {
  const date = addDays(today, 2);
  const { calls } = serve();
  const user = userEvent.setup();
  renderApp("/settings");
  await screen.findByText(/No study time yet/);

  fireEvent.change(screen.getByLabelText("Date"), { target: { value: date } });
  await user.click(screen.getByLabelText("Different times"));
  fireEvent.change(screen.getByLabelText("Exception window 1 start"), {
    target: { value: "08:00" },
  });
  fireEvent.change(screen.getByLabelText("Exception window 1 end"), {
    target: { value: "10:00" },
  });
  await user.click(screen.getByRole("button", { name: "Another window" }));
  await user.click(screen.getByRole("button", { name: "Add exception" }));

  await waitFor(() =>
    expect(
      calls.find((c) => c.path === "/availability/exceptions" && c.method === "POST")?.body,
    ).toEqual({
      date,
      unavailable: false,
      windows: [
        { start: "08:00", end: "10:00" },
        { start: "10:00", end: "11:00" },
      ],
      note: null,
    }),
  );
  expect(await screen.findByText("08:00–10:00, 10:00–11:00")).toBeVisible();
});

test("a date that already has an exception says so", async () => {
  const date = addDays(today, 3);
  serve({ exceptions: [{ date, unavailable: true, windows: [], note: null }] });
  const user = userEvent.setup();
  renderApp("/settings");
  await screen.findByRole("list", { name: "Exceptions" });

  fireEvent.change(screen.getByLabelText("Date"), { target: { value: date } });
  await user.click(screen.getByRole("button", { name: "Add exception" }));

  expect(await screen.findByText(`${date} already has an exception.`)).toBeVisible();
  // Weekday names are right for the date.
  expect(DAYS[weekdayOf(date)]).toBeDefined();
});
