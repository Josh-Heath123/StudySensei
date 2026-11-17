import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockApi, noContent, type ApiCall } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { TopicNode } from "./api";
import { aModule, aTopic, aTopicMap, anAiStatus, roots } from "./fixtures";

// Patterns
//   Creational
//     Factory
//   Structural
// Queues
const TREE = roots(
  aTopic("p", "Patterns", [
    aTopic("c", "Creational", [aTopic("f", "Factory")]),
    aTopic("s", "Structural"),
  ]),
  aTopic("q", "Queues"),
);

function renderTree(tree: TopicNode[] = TREE) {
  const api = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => tree,
    "GET /modules/:id/topic-map": () => aTopicMap(),
    "GET /ai/status": () => anAiStatus(),
    "POST /modules/:id/topics": ({ body }) =>
      json({ ...aTopic("new", "x"), ...(body as object) }, 201),
    "PATCH /topics/:id": ({ body }) => ({ ...aTopic("x", "x"), ...(body as object) }),
    "POST /topics/:id/move": () => aTopic("x", "x"),
    "DELETE /topics/:id": () => noContent(),
  });
  renderApp("/modules/m1?tab=topics");
  return { ...api, user: userEvent.setup() };
}

const lastCall = (calls: ApiCall[], method: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path.startsWith("/topics"));

test("renders the topic tree nested", async () => {
  renderTree();

  const roots = await screen.findByRole("list", { name: "Topics" });
  const patterns = within(roots).getByRole("list", { name: "Subtopics of Patterns" });
  expect(within(patterns).getByRole("list", { name: "Subtopics of Creational" })).toHaveTextContent(
    "Factory",
  );
  expect(within(roots).getByRole("button", { name: "Queues" })).toBeInTheDocument();
});

test("adds a top-level topic and a subtopic", async () => {
  const { calls, user } = renderTree();

  await user.type(await screen.findByLabelText("New topic"), "Microservices{Enter}");
  await waitFor(() =>
    expect(calls.find((c) => c.method === "POST" && c.path === "/modules/m1/topics")?.body).toEqual(
      { name: "Microservices", parent_id: null },
    ),
  );

  await user.click(screen.getByRole("button", { name: "Add subtopic to: Queues" }));
  await user.type(screen.getByLabelText("New subtopic of Queues"), "Kafka{Enter}");
  await waitFor(() =>
    expect(
      calls.filter((c) => c.method === "POST" && c.path === "/modules/m1/topics").at(-1)?.body,
    ).toEqual({ name: "Kafka", parent_id: "q" }),
  );
});

test("renames on Enter and cancels on Escape", async () => {
  const { calls, user } = renderTree();

  await user.click(await screen.findByRole("button", { name: "Rename: Queues" }));
  await user.keyboard("{Escape}");
  expect(lastCall(calls, "PATCH")).toBeUndefined();

  await user.click(screen.getByRole("button", { name: "Rename: Queues" }));
  const input = screen.getByLabelText("Rename Queues");
  await user.clear(input);
  await user.type(input, "Message queues{Enter}");

  await waitFor(() => expect(lastCall(calls, "PATCH")).toBeDefined());
  await user.tab(); // a blur after saving must not save again
  expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(1);
  expect(lastCall(calls, "PATCH")).toMatchObject({
    path: "/topics/q",
    body: { name: "Message queues" },
  });
});

test("indent, outdent and reorder send the right move", async () => {
  const { calls, user } = renderTree();
  const move = async (label: string) => {
    await user.click(await screen.findByRole("button", { name: label }));
    await waitFor(() => expect(lastCall(calls, "POST")).toBeDefined());
    const call = lastCall(calls, "POST")!;
    calls.length = 0;
    return call;
  };

  expect(await move("Indent: Queues")).toMatchObject({
    path: "/topics/q/move",
    body: { parent_id: "p", position: 2 },
  });
  expect(await move("Outdent: Structural")).toMatchObject({
    path: "/topics/s/move",
    body: { parent_id: null, position: 1 },
  });
  expect(await move("Move up: Queues")).toMatchObject({
    path: "/topics/q/move",
    body: { parent_id: null, position: 0 },
  });
});

test("moves that make no sense are disabled", async () => {
  renderTree();

  expect(await screen.findByRole("button", { name: "Move up: Patterns" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Indent: Patterns" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Outdent: Patterns" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Move down: Queues" })).toBeDisabled();
});

test("deleting asks first and mentions subtopics", async () => {
  const { calls, user } = renderTree();

  await user.click(await screen.findByRole("button", { name: "Delete: Patterns" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete “Patterns”?" });
  expect(dialog).toHaveTextContent("also deletes its 3 subtopics");
  await user.click(within(dialog).getByRole("button", { name: "Delete topic" }));

  await waitFor(() => expect(lastCall(calls, "DELETE")?.path).toBe("/topics/p"));
});

test("shows the server's message when a move fails", async () => {
  mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => TREE,
    "GET /modules/:id/topic-map": () => aTopicMap(),
    "GET /ai/status": () => anAiStatus(),
    "POST /topics/:id/move": () =>
      json({ detail: "A topic can't be moved under itself or one of its subtopics" }, 422),
  });
  renderApp("/modules/m1?tab=topics");

  await userEvent.click(await screen.findByRole("button", { name: "Indent: Queues" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("can't be moved under itself");
});
