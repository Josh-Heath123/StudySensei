import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { TopicNode } from "./api";
import { aMastery, aModule, anAiStatus, aTopic, aTopicMap, roots } from "./fixtures";
import {
  confidenceText,
  exactDuration,
  planDuration,
  subtreeWorkloadText,
  workloadShort,
  workloadText,
  type SubtreeWorkload,
  type Workload,
} from "./planningText";

const ESTIMATED: Workload = { minutes: 115, source: "estimated", slide_pages: 18, text_pages: 0 };

test("workload text says where the number came from", () => {
  expect(workloadText(ESTIMATED)).toBe("≈ 1 h 55, estimated from 18 slides");
  expect(workloadText({ ...ESTIMATED, minutes: 70, text_pages: 2 })).toBe(
    "≈ 1 h 10, estimated from 18 slides and 2 pages",
  );
  expect(workloadText({ ...ESTIMATED, minutes: 90, source: "yours" })).toBe("1 h 30 min (yours)");
  expect(workloadText({ minutes: null, source: "none", slide_pages: 0, text_pages: 0 })).toBe(
    "No estimate yet: no slides or notes are linked.",
  );
  expect(workloadShort(ESTIMATED)).toBe("≈ 1 h 55");
  expect(confidenceText(null)).toBe("Not rated");
  expect(confidenceText(4)).toBe("Confidence 4/5");
});

test("durations", () => {
  expect(planDuration(45)).toBe("45 min");
  expect(planDuration(135)).toBe("2 h 15");
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
    "GET /topics/:id/mastery": () => aMastery(),
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
  const details = within(row).getByText("≈ 1 h 55 · Not rated");
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

  expect(within(planning).getByText("≈ 1 h 55, estimated from 18 slides")).toBeVisible();
  expect(
    within(planning).getByText("Estimated at 3 minutes a slide and 6 a page of notes."),
  ).toBeVisible();
  await user.click(within(planning).getByRole("button", { name: "Set your own" }));
  const input = within(planning).getByLabelText("Your workload, in minutes");
  await user.clear(input);
  await user.type(input, "90{Enter}");

  expect(await within(planning).findByText("1 h 30 min (yours)")).toBeVisible();
  await user.click(within(planning).getByRole("button", { name: "Use the estimate" }));
  expect(await within(planning).findByText("≈ 1 h 55, estimated from 18 slides")).toBeVisible();
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

test("a chapter shows its workload with its subtopics, as the planner counts it", async () => {
  const chapter = aTopic("ch1", "Ch1", [aTopic("s1", "Firewalls")], {
    workload: { minutes: 135, source: "estimated", slide_pages: 32, text_pages: 6 },
    workload_with_subtopics: {
      minutes: 420,
      source: "estimated",
      slide_pages: 72,
      text_pages: 34,
      subtopics: 4,
    },
  });
  mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => roots(chapter),
    "GET /modules/:id/topic-map": () => aTopicMap(),
    "GET /ai/status": () => anAiStatus(),
    "GET /topics/:id/pages": () => [],
    "GET /topics/:id/mastery": () => aMastery(),
  });
  renderApp("/modules/m1?tab=topics");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Ch1" }));
  const dialog = await screen.findByRole("dialog", { name: "Ch1" });
  const planning = within(dialog).getByRole("region", { name: "Planning" });

  // Both figures in the planner's format (decision 0020), not rounded to half hours.
  expect(
    within(planning).getByText("≈ 2 h 15, estimated from 32 slides and 6 pages"),
  ).toBeVisible();
  expect(
    within(planning).getByText(
      "≈ 7 h with its 4 subtopics (estimated from 72 slides and 34 pages)",
    ),
  ).toBeVisible();
  expect(
    within(planning).getByText(
      "A figure you set here covers the whole chapter, subtopics included, when it's in an assessment.",
    ),
  ).toBeVisible();
});

test("a topic without subtopics shows no chapter figure", async () => {
  const { user } = serve();
  const dialog = await openTopic(user);
  expect(within(dialog).queryByText(/with its \d+ subtopic/)).not.toBeInTheDocument();
  expect(within(dialog).queryByText(/covers the whole chapter/)).not.toBeInTheDocument();
});

test("chapter workload text", () => {
  const whole = { minutes: 435, source: "estimated", slide_pages: 1, text_pages: 0, subtopics: 1 };
  expect(subtreeWorkloadText(whole as SubtreeWorkload)).toBe(
    "≈ 7 h 15 with its 1 subtopic (estimated from 1 slide)",
  );
  expect(subtreeWorkloadText({ ...whole, source: "yours", minutes: 60 } as SubtreeWorkload)).toBe(
    "1 h for it and its 1 subtopic (yours)",
  );
  expect(subtreeWorkloadText({ ...whole, source: "none", minutes: null } as SubtreeWorkload)).toBe(
    "No estimate with its 1 subtopic yet: no slides or notes are linked to any of them.",
  );
  expect(planDuration(65)).toBe("1 h 05");
});

async function openWithMastery(mastery: ReturnType<typeof aMastery>) {
  mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => roots(aTopic("q", "Queues", [], { workload: ESTIMATED })),
    "GET /modules/:id/topic-map": () => aTopicMap(),
    "GET /ai/status": () => anAiStatus(),
    "GET /topics/:id/pages": () => [],
    "GET /topics/:id/mastery": () => mastery,
  });
  renderApp("/modules/m1?tab=topics");
  const dialog = await openTopic(userEvent.setup());
  const planning = within(dialog).getByRole("region", { name: "Planning" });
  return within(planning).findByLabelText("Mastery");
}

test("under the starting confidence: the mastery band and what it rests on", async () => {
  const basis =
    "≈ 64 % (estimated) from recall of ≈ 78 % across 12 practised items, 9 of 14 recent " +
    "answers right, and your rating of 3 of 5.";
  const line = await openWithMastery(
    aMastery({ status: "estimated", band: "developing", value: 0.64, basis }),
  );
  expect(within(line).getByText("Developing")).toBeVisible();
  expect(within(line).getByText(basis)).toBeVisible();
});

test("with too little practice there's no band, only why", async () => {
  const basis = "Not enough practice yet: 2 of 3 attempts. Your rating of 3 of 5 is used for now.";
  const line = await openWithMastery(aMastery({ value: 0.55, band: "developing", basis }));
  expect(line).toHaveTextContent(basis);
  expect(within(line).queryByText("Developing")).not.toBeInTheDocument();
});
