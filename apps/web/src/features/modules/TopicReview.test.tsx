import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockApi, noContent, type Handler } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { LinkedMaterial, ReviewStats, TopicNode } from "./api";
import { aMastery, aModule, aTopic, aTopicMap, anAiStatus, roots } from "./fixtures";

const ai = { source: "ai" as const };
// Security (mine)
//   Firewalls (AI)
// Chapter 9 (AI)
//   Proxies (AI)
// Queues (mine)
const TREE = roots(
  aTopic("s", "Security", [aTopic("f", "Firewalls", [], ai)]),
  aTopic("c9", "Chapter 9", [aTopic("p", "Proxies", [], ai)], ai),
  aTopic("q", "Queues", [], { linked_pages: 2 }),
);
const STATS: ReviewStats = { kept: 40, renamed: 6, merged: 3, dismissed: 2, unreviewed: 3 };

function renderReview(tree: TopicNode[] = TREE, extra: Record<string, Handler> = {}) {
  const api = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => tree,
    "GET /modules/:id/topic-map": () => aTopicMap({ review: STATS }),
    "GET /ai/status": () => anAiStatus(),
    "GET /topics/:id/mastery": () => aMastery(),
    "POST /topics/:id/keep": ({ params }) => aTopic(params.id!, "x"),
    "POST /topics/:id/dismiss": () => ({ dismissed: 1 }),
    "POST /topics/:id/merge-into": ({ body }) =>
      aTopic((body as { target_id: string }).target_id, "x"),
    "POST /modules/:id/topics/keep-all": () => ({ kept: 3 }),
    ...extra,
  });
  renderApp("/modules/m1?tab=topics");
  return { ...api, user: userEvent.setup() };
}

const posts = (calls: { method: string; path: string }[]) =>
  calls.filter((c) => c.method === "POST").map((c) => c.path);

test("shows the review counter and the outcome line", async () => {
  renderReview();

  const region = await screen.findByRole("region", { name: "Topic review" });
  expect(region).toHaveTextContent("51 of 54 reviewed");
  expect(region).toHaveTextContent("Review: 40 kept, 6 renamed, 3 merged, 2 dismissed");
});

test("AI topics have Keep, Merge into and Dismiss instead of Delete", async () => {
  const { calls, user } = renderReview();

  await user.click(await screen.findByRole("button", { name: "Keep: Firewalls" }));
  await waitFor(() => expect(posts(calls)).toContain("/topics/f/keep"));

  expect(screen.queryByRole("button", { name: "Delete: Firewalls" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete: Queues" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Keep: Queues" })).not.toBeInTheDocument();
});

test("dismissing a leaf is immediate; a parent with AI subtopics asks first", async () => {
  const { calls, user } = renderReview();

  await user.click(await screen.findByRole("button", { name: "Dismiss: Proxies" }));
  await waitFor(() => expect(posts(calls)).toContain("/topics/p/dismiss"));

  await user.click(screen.getByRole("button", { name: "Dismiss: Chapter 9" }));
  const dialog = await screen.findByRole("dialog", { name: "Dismiss “Chapter 9”?" });
  expect(dialog).toHaveTextContent("also dismisses its 1 AI subtopic");
  await user.click(within(dialog).getByRole("button", { name: "Dismiss" }));
  await waitFor(() => expect(posts(calls)).toContain("/topics/c9/dismiss"));
});

test("merge into offers every topic but itself and its subtopics", async () => {
  const { calls, user } = renderReview();

  await user.click(await screen.findByRole("button", { name: "Merge into: Chapter 9" }));
  const dialog = await screen.findByRole("dialog", { name: "Merge “Chapter 9” into…" });
  const select = within(dialog).getByLabelText("Merge into");
  const options = within(select)
    .getAllByRole("option")
    .map((o) => o.textContent?.trim());
  expect(options).toEqual(["Choose a topic", "Security", "Firewalls", "Queues"]);

  await user.selectOptions(select, "s");
  await user.click(within(dialog).getByRole("button", { name: "Merge" }));

  await waitFor(() =>
    expect(calls.find((c) => c.path === "/topics/c9/merge-into")?.body).toEqual({
      target_id: "s",
    }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("the Review filter shows only AI topics and the topics holding them", async () => {
  const { user } = renderReview();
  const filter = await screen.findByRole("button", { name: "Review" });

  await user.click(filter);

  expect(filter).toHaveAttribute("aria-pressed", "true");
  const list = screen.getByRole("list", { name: "Topics" });
  expect(within(list).getByRole("button", { name: "Security" })).toBeInTheDocument();
  expect(within(list).getByRole("button", { name: "Firewalls" })).toBeInTheDocument();
  expect(within(list).queryByRole("button", { name: "Queues" })).not.toBeInTheDocument();
  // The tree is cut down, so moving is off while filtering.
  expect(screen.getByRole("button", { name: "Move down: Security" })).toBeDisabled();
});

test("Keep all remaining asks first", async () => {
  const { calls, user } = renderReview();

  await user.click(await screen.findByRole("button", { name: "Keep all remaining" }));
  const dialog = await screen.findByRole("dialog", { name: "Keep all 3 remaining AI topics?" });
  await user.click(within(dialog).getByRole("button", { name: "Keep all" }));

  await waitFor(() => expect(posts(calls)).toContain("/modules/m1/topics/keep-all"));
});

test("dismissed topics load when opened and can be restored", async () => {
  const { calls, user } = renderReview(TREE, {
    "GET /modules/:id/dismissed-topics": () => [
      { id: "d1", name: "Honeypots", dismissed_at: "2026-11-17T10:00:00Z" },
    ],
    "POST /dismissed-topics/:id/restore": () => aTopic("h", "Honeypots"),
  });
  await screen.findByRole("region", { name: "Topic review" });
  expect(calls.some((c) => c.path.endsWith("/dismissed-topics"))).toBe(false);

  await user.click(screen.getByText("Dismissed topics", { selector: "summary" }));
  await user.click(await screen.findByRole("button", { name: "Restore Honeypots" }));

  await waitFor(() => expect(posts(calls)).toContain("/dismissed-topics/d1/restore"));
});

const PAGES: LinkedMaterial[] = [
  {
    material_id: "mat1",
    title: "Week 1 Security",
    pages: [
      { page_number: 1, label: "Passwords", method: "pages", score: null },
      { page_number: 3, label: "Sessions", method: "similarity", score: 0.712 },
    ],
  },
];

test("clicking a topic lists its linked pages; a wrong one can be unlinked", async () => {
  const { calls, user } = renderReview(TREE, {
    "GET /topics/:id/pages": () => PAGES,
    "DELETE /topics/:id/pages/:material/:page": () => noContent(),
  });

  await user.click(await screen.findByRole("button", { name: "Queues" }));

  const dialog = await screen.findByRole("dialog", { name: "Queues" });
  const material = within(dialog).getByRole("region", { name: "Week 1 Security" });
  expect(material).toHaveTextContent("Page 1 · Passwords");
  expect(material).toHaveTextContent("Cited");
  expect(material).toHaveTextContent("Similar (0.71)");

  await user.click(
    within(dialog).getByRole("button", { name: "Unlink page 3 of Week 1 Security" }),
  );
  await waitFor(() =>
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/topics/q/pages/mat1/3")).toBe(
      true,
    ),
  );
});

test("a linked page opens in the page-text view", async () => {
  const { user } = renderReview(TREE, {
    "GET /topics/:id/pages": () => PAGES,
    "GET /materials/:id": () => ({
      id: "mat1",
      title: "Week 1 Security",
      content_type: "text/markdown",
    }),
    "GET /materials/:id/pages": () => [
      { page_number: 1, title: "Passwords", char_count: 20, is_scanned: false },
      { page_number: 3, title: "Sessions", char_count: 20, is_scanned: false },
    ],
    "GET /materials/:id/pages/:page": ({ params }) =>
      json({
        page_number: Number(params.page),
        title: null,
        text: `Text of page ${params.page}`,
        char_count: 14,
        is_scanned: false,
      }),
  });

  await user.click(await screen.findByRole("button", { name: "Queues" }));
  const dialog = await screen.findByRole("dialog", { name: "Queues" });
  await user.click(within(dialog).getByRole("button", { name: /Page 3/ }));

  expect(await screen.findByText("Text of page 3")).toBeInTheDocument();
});
