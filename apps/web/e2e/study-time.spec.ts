import { expect, test, type APIRequestContext } from "./base";

/**
 * Settings → Study time against the real stack: two weekly windows, then an exception, and
 * the week's total follows. The API expands availability in the user's timezone.
 */

type Row = { id: string };

/** The seeded user starts this spec with no study time and the default settings. */
async function reset(request: APIRequestContext) {
  for (const rule of (await (await request.get("/api/availability/rules")).json()) as Row[]) {
    await request.delete(`/api/availability/rules/${rule.id}`);
  }
  const exceptions = (await (await request.get("/api/availability/exceptions")).json()) as Row[];
  for (const exception of exceptions) {
    await request.delete(`/api/availability/exceptions/${exception.id}`);
  }
  await request.patch("/api/planning/settings", {
    data: { timezone: "Africa/Johannesburg", daily_study_cap_minutes: 180 },
  });
}

/** The next date (today included) that falls on `weekday` (0 is Monday), in Johannesburg. */
function nextWeekday(weekday: number): string {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Johannesburg" }).format(
    new Date(),
  );
  const date = new Date(`${today}T00:00:00Z`);
  while ((date.getUTCDay() + 6) % 7 !== weekday) date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

test.beforeEach(async ({ request }) => reset(request));
test.afterEach(async ({ request }) => reset(request));

test("two weekly windows, then an exception: the week's total changes", async ({ page }) => {
  await page.goto("/settings");
  const summary = page.getByRole("status").filter({ hasText: /study time|a week/ });
  await expect(summary).toHaveText("No study time yet: add a window to a day below.");

  // Monday 18:00-19:00, and Tuesday 18:00-21:00.
  await page.getByRole("button", { name: "Add a window on Monday" }).click();
  await expect(summary).toContainText("≈ 1 h a week available (from your rules)");
  await page.getByRole("button", { name: "Add a window on Tuesday" }).click();
  const tuesdayEnd = page.getByLabel("Tuesday window 1 end");
  await expect(tuesdayEnd).toHaveValue("19:00");
  await tuesdayEnd.fill("21:00");
  await tuesdayEnd.blur();

  await expect(summary).toContainText("≈ 4 h a week available");
  await expect(summary).toContainText("≈ 4 h in the next 7 days");

  // The coming Tuesday is off: the next 7 days lose its 3 h; the typical week doesn't.
  await page.getByLabel("Date").fill(nextWeekday(1));
  await page.getByLabel("Note (optional)").fill("Test day");
  await page.getByRole("button", { name: "Add exception" }).click();

  await expect(summary).toContainText("≈ 1 h in the next 7 days");
  await expect(summary).toContainText("≈ 4 h a week available");
  await expect(page.getByRole("list", { name: "Exceptions" })).toContainText(
    "Unavailable all day · Test day",
  );

  // After a reload it's all still there.
  await page.reload();
  await expect(summary).toContainText("≈ 1 h in the next 7 days");
  await expect(page.getByLabel("Tuesday window 1 end")).toHaveValue("21:00");
});
