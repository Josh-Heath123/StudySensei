import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { aModule, aMastery } from "@/features/modules/fixtures";
import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { PracticeItem } from "./api";
import { aGeneration, anItem, aModuleMastery, aQueue, aShortAnswer } from "./fixtures";

const HEALTH = {
  "GET /health": () => ({ status: "ok", api: "ok", database: "ok" }),
  "GET /sessions/active": () => null,
};

function itemsApi(items: PracticeItem[]) {
  let current = [...items];
  return mockApi({
    ...HEALTH,
    "GET /modules": () => [aModule()],
    "GET /modules/:id/topics": () => [],
    "GET /practice/items": () => ({ items: current, total: current.length }),
    "PATCH /practice/items/:id": ({ params, body }) => {
      current = current.map((i) => (i.id === params.id ? { ...i, ...(body as object) } : i));
      return current.find((i) => i.id === params.id);
    },
    "DELETE /practice/items/:id": ({ params }) => {
      current = current.filter((i) => i.id !== params.id);
      return new Response(null, { status: 204 });
    },
  });
}

const patches = (calls: { method: string; path: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "PATCH").map((c) => [c.path, c.body]);

async function actions(user: ReturnType<typeof userEvent.setup>, prompt: RegExp) {
  await user.click(await screen.findByRole("button", { name: prompt }));
}

test("rows show the kind, origin, state and sources, and the filters go in the URL", async () => {
  const user = userEvent.setup();
  const { calls } = itemsApi([anItem(), aShortAnswer()]);
  const { router } = renderApp("/practice/items?module=m1");

  const list = await screen.findByRole("list", { name: "Items" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(within(rows[1]!).getByText("Short answer")).toBeVisible();
  expect(within(rows[1]!).getByText("AI")).toBeVisible();
  expect(within(rows[0]!).getByText("Yours")).toBeVisible();
  expect(within(rows[0]!).getByText("New")).toBeVisible();
  expect(
    within(rows[1]!).getByRole("button", { name: /Open CH05 Hashing at page 14/ }),
  ).toBeVisible();

  await user.selectOptions(screen.getByRole("combobox", { name: "Kind" }), "short_answer");
  await waitFor(() => expect(router.state.location.search).toContain("kind=short_answer"));
  const listed = calls.filter((c) => c.path === "/practice/items").length;
  expect(listed).toBeGreaterThanOrEqual(2);
});

test("suspend, then restore", async () => {
  const user = userEvent.setup();
  const { calls } = itemsApi([anItem()]);
  renderApp("/practice/items");
  await actions(user, /Actions for "What does a hash table store\?"/);
  await user.click(await screen.findByRole("menuitem", { name: "Suspend" }));
  expect(await screen.findByText("Suspended: it's left out of reviews.")).toBeVisible();
  expect(await screen.findByText("Suspended", { selector: "[data-slot=badge]" })).toBeVisible();
  await actions(user, /Actions for/);
  await user.click(await screen.findByRole("menuitem", { name: "Restore" }));
  expect(patches(calls)).toEqual([
    ["/practice/items/i1", { status: "suspended" }],
    ["/practice/items/i1", { status: "active" }],
  ]);
});

test("an AI card can be rejected with a reason; the student's own can't", async () => {
  const user = userEvent.setup();
  const { calls } = itemsApi([aShortAnswer()]);
  renderApp("/practice/items");
  await actions(user, /Actions for "Why does a hash table/);
  await user.click(await screen.findByRole("menuitem", { name: "Reject…" }));
  const dialog = await screen.findByRole("dialog", { name: "Reject this card?" });
  await user.selectOptions(within(dialog).getByRole("combobox", { name: "Why?" }), "not_in_source");
  await user.click(within(dialog).getByRole("button", { name: "Reject" }));
  await waitFor(() =>
    expect(patches(calls)).toEqual([
      ["/practice/items/i2", { status: "rejected", reject_reason: "not_in_source" }],
    ]),
  );
  expect(await screen.findByText("Card rejected.")).toBeVisible();
});

test("the student's own card has no Reject, and Delete asks first", async () => {
  const user = userEvent.setup();
  const { calls } = itemsApi([anItem()]);
  renderApp("/practice/items");
  await actions(user, /Actions for/);
  expect(screen.queryByRole("menuitem", { name: "Reject…" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: "Delete…" }));
  const confirm = await screen.findByRole("dialog", { name: "Delete this card?" });
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  await user.click(within(confirm).getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  expect(
    await screen.findByText("No items match. Add a card, or generate practice for a topic."),
  ).toBeVisible();
});

test("editing a card saves its text", async () => {
  const user = userEvent.setup();
  const { calls } = itemsApi([anItem()]);
  renderApp("/practice/items");
  await actions(user, /Actions for/);
  await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
  const dialog = await screen.findByRole("dialog", { name: "Edit card" });
  const front = within(dialog).getByRole("textbox", { name: "Front" });
  await user.clear(front);
  await user.type(front, "What is a hash table?");
  await user.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(patches(calls)).toHaveLength(1));
  expect(patches(calls)[0]![1]).toMatchObject({
    prompt: "What is a hash table?",
    key_points: null,
  });
});

test("Add a card: a short answer needs its key points, one per line", async () => {
  const user = userEvent.setup();
  const { calls } = mockApi({
    ...HEALTH,
    "GET /modules": () => [aModule()],
    "GET /modules/:id/topics": () => [],
    "GET /practice/items": () => ({ items: [], total: 0 }),
    "POST /practice/items": ({ body }) => anItem(body as Partial<PracticeItem>),
  });
  renderApp("/practice/items");
  await user.click(await screen.findByRole("button", { name: "Add a card" }));
  const dialog = await screen.findByRole("dialog", { name: "Add a card" });
  await user.click(within(dialog).getByRole("radio", { name: "Short answer" }));
  await user.type(within(dialog).getByRole("textbox", { name: "Question" }), "Why salt?");
  await user.type(
    within(dialog).getByRole("textbox", { name: "Reference answer" }),
    "So equal passwords hash differently.",
  );
  const add = within(dialog).getByRole("button", { name: "Add card" });
  expect(add).toBeDisabled();
  await user.type(
    within(dialog).getByRole("textbox", { name: "Key points, one per line (1 to 5)" }),
    "Equal passwords differ{Enter}{Enter}Defeats rainbow tables",
  );
  await user.click(add);
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    module_id: "m1",
    topic_id: null,
    kind: "short_answer",
    prompt: "Why salt?",
    answer: "So equal passwords hash differently.",
    key_points: ["Equal passwords differ", "Defeats rainbow tables"],
  });
});

// --- /practice -----------------------------------------------------------------------

test("Practice: the counts, Start review, and topics weakest first with a band only when estimated", async () => {
  mockApi({
    ...HEALTH,
    "GET /modules": () => [aModule()],
    "GET /practice/queue": () =>
      aQueue([], { due_now: 4, new_today_left: 12, new_allowance_left: 17, new_total: 12 }),
    "GET /modules/:id/mastery": () =>
      aModuleMastery("m1", [
        aMastery({
          topic_id: "t1",
          name: "Sorting",
          status: "estimated",
          band: "strong",
          value: 0.86,
          basis: "≈ 86 % (estimated) from recall in a week ≈ 90 % across 6 practised items.",
        }),
        aMastery({
          topic_id: "t2",
          name: "Hashing",
          status: "estimated",
          band: "weak",
          value: 0.31,
          basis: "≈ 31 % (estimated) from recall in a week ≈ 40 % across 3 practised items.",
        }),
        aMastery({ topic_id: "t3", name: "Graphs", value: 0.5, band: null }),
      ]),
  });
  renderApp("/practice");

  const reviews = await screen.findByLabelText("Reviews");
  expect(await within(reviews).findByText("4")).toBeVisible();
  expect(within(reviews).getByText("12")).toBeVisible();
  expect(
    within(reviews).getByText("17 of today's new allowance left · 12 new cards waiting"),
  ).toBeVisible();
  expect(within(reviews).getByText("Now")).toBeVisible();
  expect(screen.getByRole("link", { name: "Start review" })).toHaveAttribute(
    "href",
    "/practice/review",
  );

  const names = (await screen.findAllByRole("heading", { level: 3 })).map((h) => h.textContent);
  expect(names).toEqual(["Hashing", "Graphs", "Sorting"]);
  expect(screen.getByText("Weak")).toBeVisible();
  expect(screen.getByText("Strong")).toBeVisible();
  expect(screen.queryByText("Developing")).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "0 active items" })[0]).toHaveAttribute(
    "href",
    "/practice/items?module=m1&topic=t2",
  );
});

test("Generate practice follows its generation until it's written", async () => {
  const user = userEvent.setup();
  let polls = 0;
  const { calls } = mockApi({
    ...HEALTH,
    "GET /modules": () => [aModule()],
    "GET /practice/queue": () => aQueue(),
    "GET /modules/:id/mastery": () => aModuleMastery(),
    "POST /topics/:id/practice/generate": () => aGeneration({ status: "queued", produced: 0 }),
    "GET /topics/:id/practice/generations": () => [
      polls++ === 0
        ? aGeneration({ status: "running", produced: 0 })
        : aGeneration({ status: "succeeded", produced: 8 }),
    ],
  });
  renderApp("/practice");
  await user.click(await screen.findByRole("button", { name: "Generate practice for Hashing" }));
  expect(await screen.findByText(/Queued…|Writing practice…/)).toBeVisible();
  expect(await screen.findByText("8 written", {}, { timeout: 5_000 })).toBeVisible();
  expect(calls.filter((c) => c.path === "/topics/t1/practice/generate")).toHaveLength(1);
});
