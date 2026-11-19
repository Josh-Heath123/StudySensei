import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { TopicNode } from "./api";
import { aModule, anAiStatus, aTopic, aTopicMap, roots } from "./fixtures";
import {
  aboutDuration,
  confidenceText,
  exactDuration,
  workloadShort,
  workloadText,
  type Workload,
} from "./planningText";

const ESTIMATED: Workload = { minutes: 115, source: "estimated", slide_pages: 18, text_pages: 0 };

test("workload text says where the number came from", () => {
  expect(workloadText(ESTIMATED)).toBe("≈ 2 h, estimated from 18 slides");
  expect(workloadText({ ...ESTIMATED, minutes: 70, text_pages: 2 })).toBe(
    "≈ 1 h, estimated from 18 slides and 2 pages",
  );
  expect(workloadText({ ...ESTIMATED, minutes: 90, source: "yours" })).toBe("1 h 30 min (yours)");
  expect(workloadText({ minutes: null, source: "none", slide_pages: 0, text_pages: 0 })).toBe(
    "No estimate yet: no slides or notes are linked.",
  );
  expect(workloadShort(ESTIMATED)).toBe("≈ 2 h");
  expect(confidenceText(null)).toBe("Not rated");
  expect(confidenceText(4)).toBe("Confidence 4/5");
});

test("durations", () => {
  expect(aboutDuration(45)).toBe("≈ 45 min");
  expect(aboutDuration(150)).toBe("≈ 2.5 h");
  expect(exactDuration(60)).toBe("1 h");
  expect(exactDuration(95)).toBe("1 h 35 min");
});

/** One topic whose confidence and workload the fake API keeps. */
function serve() {
  let topic: TopicNode = aTopic("q", "Queues", [], { linked_pages: 18, workload: ESTIMATED });
  const api = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => roots(topic),
    "GET /modules/:id/topic-map": () => aTopicMap(),
    "GET /ai/status": () => anAiStatus(),
    "GET /topics/:id/pages": () => [],
    "PATCH /topics/:id/planning": ({ body }) => {
      const change = body as { confidence?: number | null; estimated_minutes?: number | null };
      if ("confidence" in change) topic = { ...topic, confidence: change.confidence ?? null };
      if ("estimated_minutes" in change) {
        topic = {
          ...topic,
          workload:
            change.estimated_minutes === null
              ? ESTIMATED
              : { ...ESTIMATED, minutes: change.estimated_minutes!, source: "yours" },
        };
      }
      return { topic_id: topic.id, confidence: topic.confidence, workload: topic.workload };
    },
  });
  renderApp("/modules/m1?tab=topics");
  return { ...api, user: userEvent.setup() };
}

async function openTopic(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Queues" }));
  return screen.findByRole("dialog", { name: "Queues" });
}

test("the tree keeps planning details quiet until hover or focus", async () => {
  serve();

  const row = (await screen.findByRole("button", { name: "Queues" })).parentElement!;
  const details = within(row).getByText("≈ 2 h · Not rated");
  expect(details).toHaveClass("hidden", "group-hover:inline", "group-focus-within:inline");
});

test("rate confidence in the topic's detail, and clear it", async () => {
  const { calls, user } = serve();
  const dialog = await openTopic(user);

  const planning = within(dialog).getByRole("region", { name: "Planning" });
  expect(within(planning).getByRole("radio", { name: "Not rated" })).toBeChecked();
  await user.click(within(planning).getByRole("radio", { name: "2: Shaky" }));

  await waitFor(() =>
    expect(within(planning).getByRole("radio", { name: "2: Shaky" })).toBeChecked(),
  );
  expect(within(planning).getByText("2/5: Shaky. Your own rating.")).toBeVisible();
  await user.click(within(planning).getByRole("radio", { name: "Not rated" }));
  await waitFor(() =>
    expect(within(planning).getByRole("radio", { name: "Not rated" })).toBeChecked(),
  );
  expect(calls.filter((c) => c.method === "PATCH").map((c) => c.body)).toEqual([
    { confidence: 2 },
    { confidence: null },
  ]);
});

test("override the estimate with your own minutes, then go back to it", async () => {
  const { calls, user } = serve();
  const dialog = await openTopic(user);
  const planning = within(dialog).getByRole("region", { name: "Planning" });

  expect(within(planning).getByText("≈ 2 h, estimated from 18 slides")).toBeVisible();
  expect(
    within(planning).getByText("Estimated at 3 minutes a slide and 6 a page of notes."),
  ).toBeVisible();
  await user.click(within(planning).getByRole("button", { name: "Set your own" }));
  const input = within(planning).getByLabelText("Your workload, in minutes");
  await user.clear(input);
  await user.type(input, "90{Enter}");

  expect(await within(planning).findByText("1 h 30 min (yours)")).toBeVisible();
  await user.click(within(planning).getByRole("button", { name: "Use the estimate" }));
  expect(await within(planning).findByText("≈ 2 h, estimated from 18 slides")).toBeVisible();
  expect(calls.filter((c) => c.method === "PATCH").map((c) => c.body)).toEqual([
    { estimated_minutes: 90 },
    { estimated_minutes: null },
  ]);
});

test("a workload under 5 minutes can't be saved", async () => {
  const { user } = serve();
  const dialog = await openTopic(user);
  const planning = within(dialog).getByRole("region", { name: "Planning" });

  await user.click(within(planning).getByRole("button", { name: "Set your own" }));
  const input = within(planning).getByLabelText("Your workload, in minutes");
  await user.clear(input);
  await user.type(input, "3");

  expect(within(planning).getByRole("button", { name: "Save" })).toBeDisabled();
});
