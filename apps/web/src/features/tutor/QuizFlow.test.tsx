import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockApi } from "@/test/mockApi";

import type { Conversation, StoredMessage } from "./api";
// Loaded up front: the panel loads it lazily.
import "./AnswerMarkdown";
import { firstUnanswered, isRight, score, withAnswer, type Quiz } from "./quiz";
import { TutorDock } from "./TutorDock";

const MODULE = "mod-1";
const SESSION = "sess-1";
const MATERIAL = "mat-1";

const QUIZ: Quiz = {
  questions: [1, 2, 3].map((n) => ({
    prompt: `Question ${n}: what does a stateful firewall keep?`,
    options: ["Nothing", "A state table", "Only ports", "Only addresses"],
    correct: 1,
    explanation: `It keeps a state table of connections [S${n === 3 ? 2 : 1}].`,
    sources: [n === 3 ? "S2" : "S1"],
  })),
};

const SOURCES = [14, 13].map((page, i) => ({
  label: `S${i + 1}`,
  rank: i + 1,
  material_id: MATERIAL,
  material_title: "CH09",
  page_number: page,
  page_title: null,
  cited: true,
}));

function message(overrides: Partial<StoredMessage>): StoredMessage {
  return {
    id: "m",
    role: "user",
    mode: "answer",
    text: "",
    status: "complete",
    model: null,
    first_token_ms: null,
    total_ms: null,
    unknown_citations: [],
    created_at: "2026-11-19T10:00:00Z",
    sources: [],
    ...overrides,
  };
}

const ANSWERED = [
  message({ id: "q1", text: "How does stateful inspection work?" }),
  message({
    id: "a1",
    role: "assistant",
    text: "It keeps a state table [S1].",
    model: "groq/openai/gpt-oss-120b",
    first_token_ms: 640,
    sources: SOURCES,
  }),
];

const quizMessage = (quiz: Quiz, answers: (number | null)[] | null = null): StoredMessage =>
  message({
    id: "a2",
    role: "assistant",
    mode: "quiz",
    text: `Quiz: ${quiz.questions.length} questions.`,
    model: "groq/openai/gpt-oss-120b",
    total_ms: 3400,
    sources: SOURCES,
    quiz,
    quiz_answers: answers ?? quiz.questions.map(() => null),
  });

function conversation(messages: StoredMessage[]): Conversation {
  return {
    id: "conv-1",
    module_id: MODULE,
    study_session_id: SESSION,
    topic_id: null,
    created_at: "2026-11-19T10:00:00Z",
    messages,
  };
}

/** One session's conversation, answered once; "Quiz me" replies with \`reply\`. */
function serve(
  reply: () => Response | StoredMessage | Promise<StoredMessage>,
  start: StoredMessage[] = ANSWERED,
) {
  let messages = start;
  return mockApi({
    "GET /modules/:moduleId/tutor/conversations": () => [conversation(messages)],
    "POST /conversations/:id/quiz": async () => {
      const result = await reply();
      if (result instanceof Response) return result;
      messages = [...messages, message({ id: "q2", mode: "quiz", text: "Quiz me" }), result];
      return json(result, 201);
    },
    "PATCH /messages/:id/quiz-answers": ({ body }) => {
      const answers = (body as { answers: (number | null)[] }).answers;
      messages = messages.map((m) => (m.id === "a2" ? { ...m, quiz_answers: answers } : m));
      return messages.find((m) => m.id === "a2");
    },
    "POST /conversations/:id/messages": ({ body }) => {
      const asked = body as { question: string; mode: string };
      const events = [
        ["sources", { sources: SOURCES }],
        ["delta", { text: `In other words [S1]. (${asked.mode})` }],
        [
          "done",
          {
            message_id: "a3",
            status: "complete",
            model: "groq/openai/gpt-oss-120b",
            first_token_ms: 500,
            total_ms: 900,
            cited: ["S1"],
            unknown_citations: [],
          },
        ],
      ] as const;
      return new Response(
        events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
        { headers: { "Content-Type": "text/event-stream" } },
      );
    },
  });
}

function renderDock() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TutorDock moduleId={MODULE} sessionId={SESSION} topicId={null} />
    </QueryClientProvider>,
  );
}

const option = (letter: string) =>
  screen.getByRole("button", { name: new RegExp(`^${letter}\\. `) });

describe("grading is code", () => {
  test("right, score, the first unanswered, and a new pick", () => {
    const [q1, q2] = QUIZ.questions;
    expect(isRight(q1!, 1)).toBe(true);
    expect(isRight(q1!, 0)).toBe(false);
    expect(isRight(q2!, null)).toBe(false);
    expect(score(QUIZ, [1, 0, null])).toEqual({ right: 1, answered: 2 });
    expect(firstUnanswered(QUIZ, [1, null, null])).toBe(1);
    expect(firstUnanswered(QUIZ, [1, 0, 2])).toBe(3);
    expect(withAnswer(QUIZ, [1], 2, 3)).toEqual([1, null, 3]);
  });
});

test("Quiz me: one question at a time, graded, explained, then the results", async () => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  // The reply is held, to see the waiting state.
  const api = serve(async () => {
    await gate;
    return quizMessage(QUIZ);
  });
  const user = userEvent.setup();
  renderDock();

  const modes = await screen.findByRole("group", { name: "Follow up on this answer" });
  await user.click(within(modes).getByRole("button", { name: "Quiz me" }));
  expect(await screen.findByText("Writing 3 questions…")).toBeVisible();
  expect(within(modes).getByRole("button", { name: "Explain differently" })).toBeDisabled();
  release();

  expect(await screen.findByText("Question 1 of 3")).toBeVisible();
  // A wrong pick: the right one is shown, and why, with its citation chip.
  await user.click(option("A"));
  expect(screen.getByText("Not quite: the answer is B.")).toBeVisible();
  expect(option("A")).toHaveAccessibleName("A. Nothing (your answer)");
  expect(option("B")).toHaveAccessibleName("B. A state table (correct answer)");
  const quiz = screen.getByRole("region", { name: "Quiz" });
  expect(
    await within(quiz).findByRole("button", { name: "Source S1: CH09 · page 14" }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Next" }));

  await user.click(await screen.findByRole("button", { name: /^B. / }));
  expect(screen.getByText("Right.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Next" }));
  await user.click(await screen.findByRole("button", { name: /^B. / }));
  await user.click(screen.getByRole("button", { name: "See how you did" }));

  const results = screen.getByRole("region", { name: "Quiz results" });
  expect(results).toHaveTextContent("You got 2 of 3 right.");
  // Each question marked in words, with the student's pick beside the right one.
  const rows = within(results).getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent(
    "Wrong · Question 1: what does a stateful firewall keep?" +
      "Your answer: A. Nothing · Correct: B. A state table",
  );
  expect(rows[1]).toHaveTextContent("Right · Question 2");
  expect(rows[1]).toHaveTextContent("Your answer: B. A state table");
  expect(rows[1]).not.toHaveTextContent("Correct:");
  expect(results).toHaveTextContent("Practice only: this doesn't change your progress or plan.");
  const saved = api.calls.filter((c) => c.method === "PATCH").map((c) => c.body);
  expect(saved).toEqual([
    { answers: [0, null, null] },
    { answers: [0, 1, null] },
    { answers: [0, 1, 1] },
  ]);
});

test("after a reload the quiz comes back at the first question not answered", async () => {
  serve(
    () => quizMessage(QUIZ),
    [
      ...ANSWERED,
      message({ id: "q2", mode: "quiz", text: "Quiz me" }),
      quizMessage(QUIZ, [1, null, null]),
    ],
  );
  renderDock();

  expect(await screen.findByText("Question 2 of 3")).toBeVisible();
  expect(screen.getByText("Written by gpt-oss-120b (Groq) · in 3.4 s (measured)")).toBeVisible();
});

test("a finished quiz comes back as its results", async () => {
  serve(
    () => quizMessage(QUIZ),
    [
      ...ANSWERED,
      message({ id: "q2", mode: "quiz", text: "Quiz me" }),
      quizMessage(QUIZ, [1, 1, 0]),
    ],
  );
  renderDock();

  expect(await screen.findByRole("region", { name: "Quiz results" })).toHaveTextContent(
    "You got 2 of 3 right.",
  );
});

test("fewer than 3 grounded questions says so", async () => {
  serve(() => quizMessage({ questions: QUIZ.questions.slice(0, 1) }));
  const user = userEvent.setup();
  renderDock();

  await user.click(await screen.findByRole("button", { name: "Quiz me" }));

  expect(await screen.findByText("Question 1 of 1")).toBeVisible();
  expect(screen.getByText("Only 1 question could be based on your sources.")).toBeVisible();
});

test("a quiz the AI couldn't write reads plainly, with Retry", async () => {
  let calls = 0;
  serve(() =>
    ++calls === 1
      ? message({
          id: "a2",
          role: "assistant",
          mode: "quiz",
          status: "failed",
          text: "None of the questions it wrote were based on your sources.",
          sources: SOURCES,
        })
      : quizMessage(QUIZ),
  );
  const user = userEvent.setup();
  renderDock();

  await user.click(await screen.findByRole("button", { name: "Quiz me" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "None of the questions it wrote were based on your sources.",
  );
  await user.click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByText("Question 1 of 3")).toBeVisible();
});

test("busy providers say when to try again", async () => {
  serve(
    () =>
      new Response(JSON.stringify({ detail: "The AI providers can't take this request now." }), {
        status: 503,
        headers: { "Content-Type": "application/json", "Retry-After": "120" },
      }),
  );
  const user = userEvent.setup();
  renderDock();

  await user.click(await screen.findByRole("button", { name: "Quiz me" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    /^The free AI providers are busy; try again at \d{1,2}:\d{2}/,
  );
});

test("Explain differently and Give an example stream on the same answer", async () => {
  const api = serve(() => quizMessage(QUIZ));
  const user = userEvent.setup();
  renderDock();

  await user.click(await screen.findByRole("button", { name: "Explain differently" }));
  const log = screen.getByRole("log", { name: "Tutor conversation" });
  await within(log).findByText(/\(explain_differently\)/);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Give an example" })).toBeEnabled(),
  );
  await user.click(screen.getByRole("button", { name: "Give an example" }));
  await within(log).findByText(/\(example\)/);

  const asked = api.calls.filter((c) => c.path === "/conversations/conv-1/messages");
  expect(asked.map((c) => c.body)).toEqual([
    { question: "Explain that differently.", mode: "explain_differently" },
    { question: "Give me an example of that.", mode: "example" },
  ]);
});
