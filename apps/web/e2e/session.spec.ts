import { expect, test, type Page } from "./base";

import { uniqueCode } from "./env";

const SEC = 1000;
const MIN = 60 * SEC;

/** Let `ms` pass with the page open; every redraw (1 s) fires along the way. */
async function pass(page: Page, ms: number) {
  await page.clock.runFor(ms);
}

test("start → pause → resume → reload → break → end → reflect → summary", async ({
  page,
  request,
}, testInfo) => {
  // About 22 s in CI, but close to the 30 s default on a busy Windows laptop.
  test.setTimeout(60_000);
  // A module with a topic, made through the real API.
  const module = await (
    await request.post("/api/modules", {
      data: { code: uniqueCode("E2E101", testInfo), name: "End-to-end testing", colour: "#5EE0B0" },
    })
  ).json();
  const topic = await (
    await request.post(`/api/modules/${module.id}/topics`, { data: { name: "Fake clocks" } })
  ).json();

  // The browser's clock starts three hours ago, so the session's events (which
  // the server refuses if they're in the future) stay in the past however far we run.
  const start = Date.now() - 3 * 60 * MIN;
  await page.clock.install({ time: start });
  await page.goto("/");

  // The clock keeps running while the dialog loads: the app's data layer delivers results
  // through timers, so a paused clock would starve it (switching to this run's module, when
  // an earlier run's module is the default, never showed its topics).
  await page.getByRole("button", { name: "Start session" }).click();
  const dialog = page.getByRole("dialog", { name: "Start a study session" });
  await dialog.getByLabel("Module").selectOption(module.id);
  await dialog.getByLabel("Topic (optional)").selectOption(topic.id);
  // Frozen from here: only runFor moves time, so the numbers below are exact.
  await page.clock.pauseAt(start + MIN);
  await dialog.getByRole("button", { name: "Start" }).click();

  const timer = page.getByRole("timer");
  await expect(page).toHaveURL(/\/session$/);
  await expect(page.getByRole("heading", { level: 1, name: "Fake clocks" })).toBeVisible();
  await expect(timer).toHaveText("50:00");

  await pass(page, 10 * MIN);
  await expect(timer).toHaveText("40:00");
  await expect(page).toHaveTitle("40:00 focus · StudySensei");

  await page.getByRole("button", { name: "Pause" }).click();
  await pass(page, 5 * MIN);
  await expect(timer).toHaveText("40:00");
  await page.getByRole("button", { name: "Resume" }).click();
  await pass(page, 20 * MIN);
  await expect(timer).toHaveText("20:00");

  // A reload lands back in the running session.
  await page.reload();
  await expect(timer).toHaveText(/^(20:00|19:5d)$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await pass(page, 20 * MIN);
  await expect(page.getByText("Break due.")).toBeVisible();
  await page.getByRole("button", { name: "Break now" }).click();
  await expect(timer).toHaveText("10:00");
  await pass(page, 10 * MIN);
  await page.getByRole("button", { name: "End break" }).click();
  await page.getByRole("button", { name: "End session" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "How did it go?" })).toBeVisible();
  await page
    .getByRole("group", { name: "How focused were you?" })
    .getByText("4", { exact: true })
    .click();
  await page.getByLabel("What I covered").fill("Playwright's clock API");
  await expect(page.getByRole("checkbox", { name: "Fake clocks" })).toBeChecked();
  await page
    .getByRole("group", { name: "Confidence in Fake clocks" })
    .getByText("5", { exact: true })
    .click();
  await page.getByRole("button", { name: "Save reflection" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Session summary" })).toBeVisible();
  await expect(page.getByText("Active time").locator("..")).toContainText("50 min");
  await expect(page.getByText("Break time").locator("..")).toContainText("10 min");
  await expect(page.getByText("Measured · from 6 timer events").first()).toBeVisible();

  // The server has the whole session and its reflection.
  const history = await (await request.get(`/api/modules/${module.id}/sessions`)).json();
  const sessions = history.items;
  expect(sessions).toHaveLength(1);
  expect(sessions[0]).toMatchObject({
    state: "ended",
    topic_id: topic.id,
    focus_rating: 4,
    covered_notes: "Playwright's clock API",
    topic_ratings: [{ topic_id: topic.id, confidence: 5 }],
  });
  expect(Math.round(sessions[0].active_seconds / 60)).toBe(50);

  await page.getByRole("link", { name: "Back to Today" }).click();
  await expect(page.getByRole("button", { name: "Start session" })).toBeVisible();
});
