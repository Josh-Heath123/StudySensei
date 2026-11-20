import { expect, test, type APIRequestContext, type Page } from "./base";

import { uniqueCode } from "./env";

/**
 * The week view against the real stack (decision 0022): study time and an assessment through
 * the API, then drag a block to a free slot (it moves) and onto another block (refused, with
 * the server's sentence, and it snaps back), skip one from its popover, and start a session
 * from Today's card, end it, and see the block done on /plan.
 */

const TZ = "Africa/Johannesburg";
const PX_PER_MINUTE = 1.1;

type Block = {
  id: string;
  start: string;
  end: string;
  kind: string;
  status: string;
  minutes: number;
  actions: { start: boolean; skip: boolean; move: boolean };
};
type Row = { id: string };

/** Local date and minutes after midnight in Johannesburg. */
function local(iso: string): { date: string; minutes: number } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: Number(parts.hour) * 60 + Number(parts.minute),
  };
}

const clock = (m: number) =>
  `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

async function clearStudyTime(request: APIRequestContext) {
  for (const rule of (await (await request.get("/api/availability/rules")).json()) as Row[]) {
    await request.delete(`/api/availability/rules/${rule.id}`);
  }
  for (const e of (await (await request.get("/api/availability/exceptions")).json()) as Row[]) {
    await request.delete(`/api/availability/exceptions/${e.id}`);
  }
}

let assessmentId: string | null = null;

test.afterEach(async ({ request }) => {
  // Leave Today's card unplanned for the specs after this one.
  if (assessmentId) await request.delete(`/api/assessments/${assessmentId}`);
  assessmentId = null;
  await clearStudyTime(request);
  await request.post("/api/plan/replan");
});

/** The current week's blocks, fresh from the API. */
async function blocks(request: APIRequestContext): Promise<Block[]> {
  const today = local(new Date().toISOString()).date;
  const plan = await (await request.get(`/api/plan?from=${today}&to=${today}`)).json();
  const from = plan.first as string;
  const wide = await (
    await request.get(
      `/api/plan?from=${from}&to=${new Date(Date.parse(from) + 13 * 864e5).toISOString().slice(0, 10)}`,
    )
  ).json();
  return wide.blocks as Block[];
}

/** Monday of a local date's week. */
function mondayOf(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

/** Show the week holding `date` on /plan (This week, or Next week). */
async function showWeekOf(page: Page, date: string) {
  const thisMonday = mondayOf(local(new Date().toISOString()).date);
  if (mondayOf(date) !== thisMonday) await page.getByRole("button", { name: "Next week" }).click();
}

/** Drag a block's card to `minutes` on `date` with the mouse (pointer events). */
async function drag(page: Page, block: Block, date: string, minutes: number) {
  const card = page.locator(`[data-block-id="${block.id}"]`);
  const from = (await card.boundingBox())!;
  const column = page.locator(`[data-date="${date}"]`);
  const band = column.locator("[data-free-band]").first();
  const bandBox = (await band.boundingBox())!;
  // The first band starts at 18:00 (the only window), the grid's first hour.
  const x = bandBox.x + bandBox.width / 2;
  const y = bandBox.y + (minutes - 18 * 60) * PX_PER_MINUTE + 5;
  await page.mouse.move(from.x + from.width / 2, from.y + 5);
  await page.mouse.down();
  await page.mouse.move(x, y, { steps: 12 });
  await page.mouse.up();
}

test("drag to move, a refused drop, skip, and a planned session from Today", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(90_000);
  await clearStudyTime(request);
  await request.patch("/api/planning/settings", {
    data: { timezone: TZ, daily_study_cap_minutes: 180 },
  });
  for (let weekday = 0; weekday < 7; weekday++) {
    await request.post("/api/availability/rules", {
      data: { weekday, start: "18:00", end: "21:00" },
    });
  }
  const module = await (
    await request.post("/api/modules", {
      data: { code: uniqueCode("PLN101", testInfo), name: "Planning", colour: "#8FB8FF" },
    })
  ).json();
  const topic = await (
    await request.post(`/api/modules/${module.id}/topics`, { data: { name: "Spaced blocks" } })
  ).json();
  await request.patch(`/api/topics/${topic.id}/planning`, { data: { estimated_minutes: 300 } });
  const assessment = await (
    await request.post(`/api/modules/${module.id}/assessments`, {
      data: {
        title: "Planner test",
        kind: "test",
        due_at: new Date(Date.now() + 9 * 864e5).toISOString(),
        topic_ids: [topic.id],
      },
    })
  ).json();
  assessmentId = assessment.id;
  await request.post("/api/plan/replan");

  // --- a valid drag: a study block to a clear evening slot ---
  const all = await blocks(request);
  const movable = all.filter((b) => b.kind === "study" && b.actions.move);
  expect(movable.length).toBeGreaterThan(1);
  const block = movable.at(-1)!;
  const due = local(assessment.due_at);
  let target: { date: string; minutes: number } | null = null;
  const tomorrow = local(new Date(Date.now() + 864e5).toISOString()).date;
  for (const candidate of [...new Set(all.map((b) => local(b.start).date))].sort()) {
    if (candidate < tomorrow || candidate >= due.date) continue;
    if (mondayOf(candidate) !== mondayOf(local(block.start).date)) continue;
    const others = all.filter((b) => b.id !== block.id && local(b.start).date === candidate);
    if (others.length > 1) continue;
    for (let t = 18 * 60; t + 50 <= 21 * 60; t += 5) {
      if (others.every((b) => Math.abs(local(b.start).minutes - t) >= 60)) {
        if (
          candidate !== local(block.start).date ||
          Math.abs(local(block.start).minutes - t) >= 60
        ) {
          target = { date: candidate, minutes: t };
          break;
        }
      }
    }
    if (target) break;
  }
  expect(target, "a clear slot in the block's week").not.toBeNull();

  await page.goto("/plan");
  await showWeekOf(page, local(block.start).date);
  await expect(page.locator(`[data-block-id="${block.id}"]`)).toBeVisible();
  await drag(page, block, target!.date, target!.minutes);
  await expect(page.getByText(/You moved Spaced blocks from .* to .*\./)).toBeVisible();
  const moved = page
    .locator(`[data-date="${target!.date}"]`)
    .getByRole("button", { name: new RegExp(`^Spaced blocks, ${clock(target!.minutes)} to`) });
  await expect(moved).toBeVisible();

  // --- an invalid drop: onto another block, refused with the server's sentence ---
  const now = await blocks(request);
  const pinned = now.find(
    (b) => local(b.start).date === target!.date && local(b.start).minutes === target!.minutes,
  )!;
  const other = now.find(
    (b) =>
      b.id !== pinned.id &&
      b.kind === "study" &&
      b.status === "planned" &&
      local(b.start).date >= tomorrow &&
      mondayOf(local(b.start).date) === mondayOf(target!.date),
  )!;
  await drag(page, pinned, local(other.start).date, local(other.start).minutes);
  await expect(page.getByRole("alert")).toHaveText("Leave 10 minutes between blocks.");
  await expect(moved).toBeVisible(); // snapped back

  // --- skip from the popover ---
  await page.locator(`[data-block-id="${other.id}"]`).click();
  const popover = page.getByRole("dialog", { name: "Spaced blocks" });
  await popover.getByRole("button", { name: "Skip" }).click();
  await page
    .getByRole("dialog", { name: "Skip this block?" })
    .getByRole("button", { name: "Skip" })
    .click();
  await expect(page.getByText(/You skipped Spaced blocks \(/)).toBeVisible();

  // --- start the next block from Today, end it, and see it done ---
  await page.goto("/");
  const nextUp = page.getByRole("region", { name: /Spaced blocks|Final review/ });
  await expect(nextUp).toBeVisible();
  const next = (await (await request.get("/api/plan/next")).json()) as Block;
  await nextUp.getByRole("button", { name: "Start session" }).click();
  await expect(page).toHaveURL(/\/session$/);
  await page.getByRole("button", { name: "End session" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "How did it go?" })).toBeVisible();

  await page.goto("/plan");
  await showWeekOf(page, local(next.start).date);
  await expect(page.locator(`[data-block-id="${next.id}"]`)).toContainText("(measured)");
});
