import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page, type Route } from "./base";

import { uniqueCode } from "./env";

/**
 * The follow-up modes in a real running session. Every tutor call is answered by page.route
 * from fixtures, with a small record of what the API would have stored, so the panel's
 * refetches (and the reload) see the conversation as they would for real. No AI is called
 * and nothing fake lives in the app.
 */

const FIXTURES = path.resolve(import.meta.dirname, "fixtures");
const QUIZ = JSON.parse(readFileSync(path.join(FIXTURES, "tutor-quiz.json"), "utf8"));
const MATERIAL = "00000000-0000-4000-8000-00000000000a";
const QUESTION = "How do layers differ from pipes and filters?";

type Message = Record<string, unknown>;

let sessionToDelete: string | null = null;

test.afterEach(async ({ request }) => {
  // One open session per user: leave none behind for the next spec.
  if (sessionToDelete) await request.delete(`/api/sessions/${sessionToDelete}`);
  sessionToDelete = null;
});

const sources = (cited: string[]) =>
  [
    ["S1", 1],
    ["S2", 3],
  ].map(([label, page]) => ({
    label,
    rank: Number(String(label).slice(1)),
    material_id: MATERIAL,
    material_title: "lecture",
    page_number: page,
    page_title: null,
    cited: cited.includes(String(label)),
  }));

const sse = (text: string, id: string) =>
  [
    [
      "sources",
      {
        sources: sources([]).map((s) => ({
          label: s.label,
          material_id: s.material_id,
          material_title: s.material_title,
          page_number: s.page_number,
          page_title: s.page_title,
        })),
      },
    ],
    ["delta", { text }],
    [
      "done",
      {
        message_id: id,
        status: "complete",
        model: "groq/openai/gpt-oss-120b",
        first_token_ms: 600,
        total_ms: 1500,
        cited: ["S1"],
        unknown_citations: [],
      },
    ],
  ]
    .map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");

/** The tutor API for one session, as page.route handlers over an in-memory conversation. */
async function fakeTutor(page: Page, moduleId: string, sessionId: string) {
  const conversation = {
    id: "00000000-0000-4000-8000-0000000000c1",
    module_id: moduleId,
    study_session_id: sessionId,
    topic_id: null,
    created_at: new Date().toISOString(),
    messages: [] as Message[],
  };
  let n = 0;
  let created = false;
  const message = (fields: Message): Message => ({
    id: `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`,
    mode: "answer",
    status: "complete",
    model: null,
    first_token_ms: null,
    total_ms: null,
    unknown_citations: [],
    created_at: new Date().toISOString(),
    sources: [],
    ...fields,
  });
  const answers = {
    answer: "A **layered** style stacks components; each calls only the one below it [S1].",
    explain_differently: "Think of a stack of trays: you only touch the tray under yours [S1].",
  } as Record<string, string>;

  await page.route("**/api/modules/*/tutor/conversations*", async (route: Route) => {
    if (route.request().method() === "POST") {
      created = true;
      await route.fulfill({ status: 201, json: conversation });
    } else {
      await route.fulfill({ json: created ? [conversation] : [] });
    }
  });
  await page.route("**/api/conversations/*/messages", async (route: Route) => {
    const body = route.request().postDataJSON() as { question: string; mode: string };
    const text = answers[body.mode] ?? "Unexpected mode";
    const question = message({ role: "user", text: body.question, mode: body.mode });
    const answer = message({
      role: "assistant",
      mode: body.mode,
      text,
      model: "groq/openai/gpt-oss-120b",
      first_token_ms: 600,
      total_ms: 1500,
      sources: sources(["S1"]),
    });
    conversation.messages.push(question, answer);
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: sse(text, String(answer.id)),
    });
  });
  await page.route("**/api/conversations/*/quiz", async (route: Route) => {
    const answer = message({
      role: "assistant",
      mode: "quiz",
      text: "Quiz: 3 questions.",
      model: "groq/openai/gpt-oss-120b",
      total_ms: 2400,
      sources: sources(["S1", "S2"]),
      quiz: QUIZ,
      quiz_answers: [null, null, null],
    });
    conversation.messages.push(message({ role: "user", mode: "quiz", text: "Quiz me" }), answer);
    await route.fulfill({ status: 201, json: answer });
  });
  await page.route("**/api/messages/*/quiz-answers", async (route: Route) => {
    const id = route.request().url().split("/").at(-2);
    const found = conversation.messages.find((m) => m.id === id)!;
    found.quiz_answers = (route.request().postDataJSON() as { answers: unknown[] }).answers;
    await route.fulfill({ json: found });
  });
  return conversation;
}

test("Explain differently, then Quiz me: answer all three, and a reload brings the quiz back", async ({
  page,
  request,
}, testInfo) => {
  const module = await (
    await request.post("/api/modules", {
      data: { code: uniqueCode("TUT102", testInfo), name: "Tutor modes e2e" },
    })
  ).json();
  await page.goto("/");
  await page.getByRole("button", { name: "Start session" }).click();
  const dialog = page.getByRole("dialog", { name: "Start a study session" });
  await dialog.getByLabel("Module").selectOption(module.id);
  await dialog.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/session$/);
  await expect
    .poll(async () => (await (await request.get("/api/sessions/active")).json())?.id ?? null)
    .not.toBeNull();
  const active = await (await request.get("/api/sessions/active")).json();
  sessionToDelete = active.id;
  const stored = await fakeTutor(page, module.id, active.id);

  const tutor = page.getByRole("complementary", { name: "Tutor" });
  const box = tutor.getByRole("textbox", { name: "Ask about this topic" });
  await expect(box).toBeEnabled({ timeout: 20_000 });
  await box.fill(QUESTION);
  await box.press("Enter");
  await expect(tutor).toContainText("each calls only the one below it");

  // Explain differently streams like an answer, on the same sources.
  const modes = tutor.getByRole("group", { name: "Follow up on this answer" });
  await modes.getByRole("button", { name: "Explain differently" }).click();
  await expect(tutor).toContainText("Think of a stack of trays");
  expect(stored.messages.at(-2)).toMatchObject({ mode: "explain_differently" });

  // Quiz me: one question at a time, graded here.
  await tutor
    .getByRole("group", { name: "Follow up on this answer" })
    .getByRole("button", { name: "Quiz me" })
    .click();
  const quiz = tutor.getByRole("region", { name: "Quiz" });
  await expect(quiz.getByText("Question 1 of 3")).toBeVisible();
  await quiz.getByRole("button", { name: /^B\. Only the layer below it/ }).click();
  await expect(quiz.getByText("Right.")).toBeVisible();
  await expect(quiz.getByRole("button", { name: "Source S1: lecture · page 1" })).toBeVisible();
  await quiz.getByRole("button", { name: "Next" }).click();
  await quiz.getByRole("button", { name: /^A\. Through a shared database/ }).click();
  await expect(quiz.getByText("Not quite: the answer is C.")).toBeVisible();
  await quiz.getByRole("button", { name: "Next" }).click();
  await quiz.getByRole("button", { name: /^B\. Layered/ }).click();
  await quiz.getByRole("button", { name: "See how you did" }).click();
  await expect(tutor.getByRole("region", { name: "Quiz results" })).toContainText(
    "You got 2 of 3 right.",
  );
  expect(stored.messages.at(-1)).toMatchObject({ quiz_answers: [1, 0, 1] });

  // After a reload the quiz comes back, finished.
  await page.reload();
  await expect(
    page
      .getByRole("complementary", { name: "Tutor" })
      .getByRole("region", { name: "Quiz results" }),
  ).toContainText("You got 2 of 3 right.");
});
