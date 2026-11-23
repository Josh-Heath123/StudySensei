import { expect, test, type APIRequestContext } from "./base";

import { uniqueCode } from "./env";

/**
 * Practice (Phase 5 task 4, ADR 0029) against the real API: the student's own flashcard
 * reviewed by keyboard, a short answer checked by the AI (POST /mark answered by page.route,
 * as the tutor specs do: no AI provider in e2e), and suspending and restoring an item. Each
 * test works in its own module, so the review queue is scoped to it.
 */

const KEY_POINTS = ["Stores key and value pairs", "Finds them by hashing the key"];

async function aModule(
  request: APIRequestContext,
  prefix: string,
  info: Parameters<typeof uniqueCode>[1],
) {
  const response = await request.post("/api/modules", {
    data: { code: uniqueCode(prefix, info), name: "Practice e2e" },
  });
  expect(response.ok()).toBe(true);
  return (await response.json()) as { id: string };
}

test("add your own flashcard, review it by keyboard, and see when it's next due", async ({
  page,
  request,
}, testInfo) => {
  const module = await aModule(request, "PRC101", testInfo);
  await page.goto(`/practice?module=${module.id}`);
  await expect(page.getByRole("heading", { name: "Practice", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Add a card", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Add a card" });
  await dialog.getByRole("textbox", { name: "Front" }).fill("What does a stack return first?");
  await dialog.getByRole("textbox", { name: "Back" }).fill("The item pushed last (LIFO).");
  await dialog.getByRole("button", { name: "Add card" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(/Card added/)).toBeVisible();

  await page.getByRole("link", { name: "Start review" }).click();
  const prompt = page.getByRole("heading", { name: "What does a stack return first?" });
  await expect(prompt).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByText("The item pushed last (LIFO).")).toBeVisible();
  // A new card: Good goes to its 10-minute learning step.
  await expect(page.getByRole("button", { name: "Good, next in 10 min" })).toBeVisible();
  await page.keyboard.press("3");

  await expect(
    page.getByRole("heading", { name: /A card you're learning comes back in (9|10) min/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Finish now" }).click();
  await expect(page.getByRole("heading", { name: "1 card reviewed" })).toBeVisible();
  await expect(page.getByText("100 %")).toBeVisible();
  await expect(page.getByText(/^in (9|10) min$/)).toBeVisible();
});

test("a short answer checked by the AI: pressing its suggested grade records it as the AI's", async ({
  page,
  request,
}, testInfo) => {
  const module = await aModule(request, "PRC102", testInfo);
  const created = await request.post("/api/practice/items", {
    data: {
      module_id: module.id,
      kind: "short_answer",
      prompt: "What is a hash table?",
      answer: "A table of key and value pairs, found by hashing the key.",
      key_points: KEY_POINTS,
    },
  });
  const item = (await created.json()) as { id: string };
  let sent: unknown = null;
  await page.route("**/api/practice/items/*/mark", async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({
      json: {
        coverage: [
          { index: 1, key_point: KEY_POINTS[0], covered: true },
          { index: 2, key_point: KEY_POINTS[1], covered: false },
        ],
        verdict: "partly",
        suggested_grade: 2,
        feedback: "You say what it stores; say how it finds them.",
        model: "gemini/flash",
      },
    });
  });

  await page.goto(`/practice/review?module=${module.id}`);
  await page.getByRole("textbox", { name: "Your answer" }).fill("It stores keys and values.");
  await expect(
    page.getByText(
      "Sends your answer and the reference answer to the AI to check it. Nothing else about you.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Check with AI" }).click();
  const check = page.getByRole("region", { name: "The AI's check" });
  await expect(check.getByText("Partly right")).toBeVisible();
  await expect(check.getByText("You say what it stores; say how it finds them.")).toBeVisible();
  expect(sent).toEqual({ answer_text: "It stores keys and values." });

  await page.getByRole("button", { name: /^Hard, next in .+, suggested by the AI$/ }).click();
  await expect(page.getByRole("heading", { name: /comes back|1 card reviewed/ })).toBeVisible();

  const reviews = (await (await request.get(`/api/practice/items/${item.id}/reviews`)).json()) as {
    grade: number;
    marked_by: string;
    answer_text: string;
    ai_marking: { verdict: string } | null;
  }[];
  expect(reviews).toHaveLength(1);
  expect(reviews[0]).toMatchObject({
    grade: 2,
    marked_by: "ai",
    answer_text: "It stores keys and values.",
    ai_marking: { verdict: "partly" },
  });
});

test("suspend an item, then restore it", async ({ page, request }, testInfo) => {
  const module = await aModule(request, "PRC103", testInfo);
  await request.post("/api/practice/items", {
    data: {
      module_id: module.id,
      kind: "flashcard",
      prompt: "What is FIFO?",
      answer: "First in, first out.",
    },
  });
  await page.goto(`/practice/items?module=${module.id}`);
  const row = page.getByRole("listitem").filter({ hasText: "What is FIFO?" });
  await expect(row.getByText("New")).toBeVisible();

  await row.getByRole("button", { name: 'Actions for "What is FIFO?"' }).click();
  await page.getByRole("menuitem", { name: "Suspend" }).click();
  await expect(page.getByText("Suspended: it's left out of reviews.")).toBeVisible();
  await expect(row.getByText("Suspended", { exact: true })).toBeVisible();

  // Out of the queue while suspended.
  const queue = await (await request.get(`/api/practice/queue?module_id=${module.id}`)).json();
  expect(queue.items).toHaveLength(0);

  await row.getByRole("button", { name: 'Actions for "What is FIFO?"' }).click();
  await page.getByRole("menuitem", { name: "Restore" }).click();
  await expect(page.getByText("Restored: it's back in your reviews.")).toBeVisible();
  await expect(row.getByText("Suspended", { exact: true })).toBeHidden();
  const back = await (await request.get(`/api/practice/queue?module_id=${module.id}`)).json();
  expect(back.items).toHaveLength(1);
});
