import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { AiStatus, TopicMapStatus, TopicNode } from "./api";
import { aModule, aTopic, aTopicMap, anAiStatus, roots } from "./fixtures";

function renderTopics({
  tree = roots(aTopic("t1", "Microservices")),
  status = [aTopicMap()],
  ai = anAiStatus(),
}: { tree?: TopicNode[]; status?: TopicMapStatus[]; ai?: AiStatus } = {}) {
  let call = 0;
  const api = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => tree,
    // Each poll gets the next status (the last one repeats).
    "GET /modules/:id/topic-map": () => status[Math.min(call++, status.length - 1)],
    "POST /modules/:id/topic-map/build": () => aTopicMap({ pending: 2 }),
    "GET /ai/status": () => ai,
  });
  renderApp("/modules/m1?tab=topics");
  return { ...api, user: userEvent.setup() };
}

test("AI topics carry a badge and every topic shows its linked pages", async () => {
  renderTopics({
    tree: roots(
      aTopic("t1", "Microservices", [], { linked_pages: 1 }),
      aTopic("t2", "Security", [aTopic("t3", "Password storage", [], { source: "ai" })], {
        source: "ai",
        linked_pages: 12,
      }),
    ),
  });

  const list = await screen.findByRole("list", { name: "Topics" });
  const security = within(list).getByRole("button", { name: "Security" }).closest("li")!;
  expect(within(security).getAllByText("AI")).toHaveLength(2); // it and its subtopic
  expect(within(security).getByText("12 pages")).toBeInTheDocument();
  const own = within(list).getByRole("button", { name: "Microservices" }).closest("div")!;
  expect(within(own).queryByText("AI")).not.toBeInTheDocument();
  expect(within(own).getByText("1 page")).toBeInTheDocument();
});

test("building starts the analysis and shows progress", async () => {
  const { calls, user } = renderTopics();
  const panel = await screen.findByRole("region", { name: "AI topic map" });
  expect(within(panel).getByText("2 materials not analysed yet (0 of 2 done).")).toBeVisible();

  await user.click(within(panel).getByRole("button", { name: "Build topic map" }));

  await waitFor(() =>
    expect(calls.some((c) => c.method === "POST" && c.path === "/modules/m1/topic-map/build")).toBe(
      true,
    ),
  );
  expect(await within(panel).findByText("Analysed 0 of 2 materials…")).toBeVisible();
  expect(within(panel).getByRole("progressbar", { name: "Materials analysed" })).toHaveAttribute(
    "max",
    "2",
  );
  expect(within(panel).getByRole("button", { name: "Build topic map" })).toBeDisabled();
});

test("without an AI key the button is off and says why", async () => {
  renderTopics({ ai: anAiStatus(false) });

  const panel = await screen.findByRole("region", { name: "AI topic map" });
  expect(await within(panel).findByText(/AI isn't set up/)).toBeVisible();
  expect(within(panel).getByRole("button", { name: "Build topic map" })).toBeDisabled();
});

test("with nothing eligible it says what to upload", async () => {
  renderTopics({ status: [aTopicMap({ eligible: 0 })] });

  const panel = await screen.findByRole("region", { name: "AI topic map" });
  expect(within(panel).getByText(/Upload slides, notes/)).toBeVisible();
  expect(within(panel).getByRole("button", { name: "Build topic map" })).toBeDisabled();
});

test("a rate-limited wait is shown with failures explained", async () => {
  renderTopics({
    status: [
      aTopicMap({
        analysed: 1,
        pending: 1,
        failed: 1,
        eligible: 3,
        waiting_until: new Date(Date.now() + 3_600_000).toISOString(),
        last_error: "The AI's topic list didn't come out in the expected shape.",
      }),
    ],
  });

  const panel = await screen.findByRole("region", { name: "AI topic map" });
  expect(within(panel).getByText(/The AI is resting until/)).toBeVisible();
  expect(within(panel).getByText(/1 material couldn't be analysed/)).toBeVisible();
});
