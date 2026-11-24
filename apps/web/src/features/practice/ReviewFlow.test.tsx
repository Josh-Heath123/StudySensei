import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { PracticeItem, QueueCounts } from "./api";
import { aMarking, anItem, aPreview, aQueue, aReviewResult, aShortAnswer } from "./fixtures";
import { MARKING_PRIVACY } from "./practiceText";

const SOON = () => new Date(Date.now() + 5 * 60_000).toISOString();

/** A queue that drops an item once it's reviewed; `after` is the counts left then. */
function reviewing(items: PracticeItem[], after: Partial<QueueCounts> = {}, mark?: () => unknown) {
  let left = [...items];
  const api = mockApi({
    "GET /health": () => ({ status: "ok", api: "ok", database: "ok" }),
    "GET /sessions/active": () => null,
    "GET /practice/queue": () => aQueue(left, left.length ? { due_now: left.length } : after),
    "GET /practice/items/:id/preview": () => aPreview(),
    "POST /practice/items/:id/mark": () => (mark ? mark() : aMarking()),
    "POST /practice/items/:id/reviews": ({ params, body }) => {
      left = left.filter((i) => i.id !== params.id);
      return aReviewResult((body as { grade: number }).grade, left.length ? {} : after);
    },
  });
  renderApp("/practice/review");
  return api;
}

const reviews = (calls: { method: string; path: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "POST" && c.path.endsWith("/reviews")).map((c) => c.body);

test("a flashcard by keyboard: Space shows the answer, 3 grades it Good, then the summary", async () => {
  const user = userEvent.setup();
  const { calls } = reviewing([anItem()]);

  const prompt = await screen.findByRole("heading", { name: "What does a hash table store?" });
  await waitFor(() => expect(prompt).toHaveFocus());
  expect(screen.queryByText(/Key and value pairs/)).not.toBeInTheDocument();
  await user.keyboard(" ");
  expect(await screen.findByText(/Key and value pairs/)).toBeVisible();
  const good = await screen.findByRole("button", { name: "Good, next in 10 min" });
  expect(good).toHaveAttribute("aria-keyshortcuts", "3");
  await user.keyboard("3");

  await waitFor(() => expect(reviews(calls)).toHaveLength(1));
  expect(reviews(calls)[0]).toMatchObject({ grade: 3, marked_by: "self", ai_marking: null });
  expect((reviews(calls)[0] as { duration_ms: number }).duration_ms).toBeGreaterThanOrEqual(0);
  const summary = await screen.findByRole("heading", { name: "1 card reviewed" });
  await waitFor(() => expect(summary).toHaveFocus());
  expect(screen.getByText("100 %")).toBeVisible();
  expect(screen.getByRole("link", { name: "Back to practice" })).toHaveAttribute(
    "href",
    "/practice",
  );
});

test("a short answer checked by the AI: its coverage, feedback and suggestion; pressing it records ai", async () => {
  const user = userEvent.setup();
  const { calls } = reviewing([aShortAnswer()]);

  const answer = await screen.findByRole("textbox", { name: "Your answer" });
  expect(screen.getByText(MARKING_PRIVACY)).toBeVisible();
  expect(screen.getByRole("button", { name: "Check with AI" })).toBeDisabled();
  await user.type(answer, "It spreads keys so buckets stay short.");
  await user.click(screen.getByRole("button", { name: "Check with AI" }));

  const check = await screen.findByRole("region", { name: "The AI's check" });
  expect(within(check).getByText("Partly right")).toBeVisible();
  expect(within(check).getByText(/2 of 3 key points · checked by gemini\/flash/)).toBeVisible();
  expect(within(check).getByText("Missing:", { exact: false })).toBeInTheDocument();
  expect(within(check).getByText(/say why that keeps lookups fast/)).toBeVisible();
  expect(
    screen.getByText(/Partly right: 2 of 3 key points. The AI suggests Hard./),
  ).toBeInTheDocument();
  // The reference and its source are shown too.
  expect(screen.getByText(/It spreads keys evenly, so buckets/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Open CH05 Hashing at page 14" })).toHaveTextContent(
    "CH05 p14",
  );
  const hard = screen.getByRole("button", { name: "Hard, next in 6 min, suggested by the AI" });
  await user.click(hard);

  await waitFor(() => expect(reviews(calls)).toHaveLength(1));
  expect(reviews(calls)[0]).toMatchObject({
    grade: 2,
    marked_by: "ai",
    ai_marking: aMarking(),
    answer_text: "It spreads keys so buckets stay short.",
  });
  const marked = calls.find((c) => c.path.endsWith("/mark"));
  expect(marked?.body).toEqual({ answer_text: "It spreads keys so buckets stay short." });
});

test("choosing another grade than the AI's is the student's own, with the marking kept", async () => {
  const user = userEvent.setup();
  const { calls } = reviewing([aShortAnswer()]);
  await user.type(await screen.findByRole("textbox", { name: "Your answer" }), "All three.");
  await user.click(screen.getByRole("button", { name: "Check with AI" }));
  await user.click(await screen.findByRole("button", { name: /^Good, next in 10 min$/ }));
  await waitFor(() => expect(reviews(calls)).toHaveLength(1));
  expect(reviews(calls)[0]).toMatchObject({ grade: 3, marked_by: "self", ai_marking: aMarking() });
});

test("the reference's tick list suggests a grade from the ticks, and the student still chooses", async () => {
  const user = userEvent.setup();
  const { calls } = reviewing([aShortAnswer()]);
  await user.type(await screen.findByRole("textbox", { name: "Your answer" }), "Spreads keys.");
  await user.click(screen.getByRole("button", { name: "Show reference" }));

  const ticks = await screen.findByRole("group", { name: "Tick the key points your answer made" });
  expect(within(ticks).getByText("0 of 3 ticked: Again suggested.")).toBeInTheDocument();
  await user.click(within(ticks).getByRole("checkbox", { name: "Spreads keys evenly" }));
  await user.click(within(ticks).getByRole("checkbox", { name: "Keeps buckets short" }));
  expect(within(ticks).getByText("2 of 3 ticked: Hard suggested.")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Hard, next in 6 min, suggested by your ticks" }),
  ).toBeVisible();
  await user.click(within(ticks).getByRole("checkbox", { name: "Keeps lookups fast" }));
  expect(
    screen.getByRole("button", { name: "Good, next in 10 min, suggested by your ticks" }),
  ).toBeVisible();

  // Keys grade it once the reference is shown (focus isn't in the answer box any more).
  screen.getByRole("heading", { name: /good hash function/ }).focus();
  await user.keyboard("1");
  await waitFor(() => expect(reviews(calls)).toHaveLength(1));
  expect(reviews(calls)[0]).toMatchObject({
    grade: 1,
    marked_by: "self",
    ai_marking: null,
    answer_text: "Spreads keys.",
  });
});

test("when the AI is busy, it says so and the reference is still there", async () => {
  const user = userEvent.setup();
  const { calls } = reviewing([aShortAnswer()], {}, () =>
    json({ detail: "Every AI model is busy. Try again in 40 s." }, 503),
  );
  await user.type(await screen.findByRole("textbox", { name: "Your answer" }), "Hm.");
  await user.click(screen.getByRole("button", { name: "Check with AI" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Every AI model is busy. Try again in 40 s. You can still show the reference and mark it yourself.",
  );
  await user.click(screen.getByRole("button", { name: "Show reference" }));
  expect(await screen.findByRole("group", { name: "How well did you know it?" })).toBeVisible();
  expect(reviews(calls)).toHaveLength(0);
});

test("a learning step due soon keeps the session open until the student finishes", async () => {
  const user = userEvent.setup();
  reviewing([anItem()], { next_due_at: SOON() });
  await user.click(await screen.findByRole("button", { name: "Show answer" }));
  await user.click(await screen.findByRole("button", { name: /^Again/ }));
  expect(
    await screen.findByRole("heading", { name: /A card you're learning comes back in 5 min/ }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Finish now" }));
  expect(await screen.findByRole("heading", { name: "1 card reviewed" })).toBeVisible();
  expect(screen.getByText("0 %")).toBeVisible();
  expect(screen.getByText("in 5 min")).toBeVisible();
});

test("with nothing due, it says when the next review is", async () => {
  reviewing([], { next_due_at: new Date(Date.now() + 3 * 3_600_000).toISOString() });
  expect(await screen.findByText("Nothing to review right now")).toBeVisible();
  expect(screen.getByText("Your next review is in 3 h.")).toBeVisible();
});
