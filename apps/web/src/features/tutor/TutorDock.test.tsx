import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockApi, type Handler } from "@/test/mockApi";

import type { Conversation, StoredMessage } from "./api";
// Loaded up front: the panel loads it lazily, which on a busy machine can outlast a wait.
import "./AnswerMarkdown";
import { PRIVACY_NOTE } from "./storage";
import { TutorDock } from "./TutorDock";

const MODULE = "mod-1";
const SESSION = "sess-1";
const TOPIC = "topic-1";
const MATERIAL = "mat-1";

const SOURCES = [
  {
    label: "S1",
    material_id: MATERIAL,
    material_title: "CH09",
    page_number: 14,
    page_title: null,
  },
  {
    label: "S2",
    material_id: MATERIAL,
    material_title: "CH09",
    page_number: 13,
    page_title: "Types of firewalls",
  },
];

type Event = [string, unknown];

/** An SSE response. `hold` keeps it open (an answer still being written) until aborted. */
function sse(
  events: Event[],
  { hold = false, signal }: { hold?: boolean; signal?: AbortSignal } = {},
) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const [name, data] of events) {
        controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
      }
      if (hold) {
        signal?.addEventListener("abort", () =>
          controller.error(new DOMException("The user aborted a request.", "AbortError")),
        );
      } else {
        controller.close();
      }
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

const done = (overrides: object = {}): Event => [
  "done",
  {
    message_id: "a1",
    status: "complete",
    model: "groq/openai/gpt-oss-120b",
    first_token_ms: 640,
    total_ms: 1900,
    cited: ["S2"],
    unknown_citations: [],
    ...overrides,
  },
];

function conversation(messages: StoredMessage[] = []): Conversation {
  return {
    id: "conv-1",
    module_id: MODULE,
    study_session_id: SESSION,
    topic_id: TOPIC,
    created_at: "2026-11-19T10:00:00Z",
    messages,
  };
}

function stored(text: string, answer: Partial<StoredMessage> = {}): StoredMessage[] {
  return [
    {
      id: "q1",
      role: "user",
      mode: "answer",
      text,
      status: "complete",
      model: null,
      first_token_ms: null,
      total_ms: null,
      unknown_citations: [],
      created_at: "2026-11-19T10:00:00Z",
      sources: [],
    },
    {
      id: "a1",
      role: "assistant",
      mode: "answer",
      text: "It keeps a state table【S2】.",
      status: "complete",
      model: "groq/openai/gpt-oss-120b",
      first_token_ms: 640,
      total_ms: 1900,
      unknown_citations: [],
      created_at: "2026-11-19T10:00:01Z",
      sources: SOURCES.map((s, i) => ({ ...s, rank: i + 1, cited: s.label === "S2" })),
      ...answer,
    },
  ];
}

/**
 * The API for one session: no conversation until the first question, then the stored copy
 * after each answer (what `answers` streams, the server is assumed to have stored).
 */
/** A scripted answer: its events (held open with `hold`, as if still being written), or a
 * plain response such as an HTTP error. */
type Script = (call: Parameters<Handler>[0]) => { events: Event[]; hold?: boolean } | Response;

function serve(answers: Script[], { existing = null as Conversation | null } = {}) {
  let current = existing;
  let asked = 0;
  const api = mockApi({
    "GET /modules/:moduleId/tutor/conversations": () => (current ? [current] : []),
    "POST /modules/:moduleId/tutor/conversations": ({ body }) => {
      current = conversation();
      return json({ ...current, ...(body as object) }, 201);
    },
    "POST /conversations/:id/messages": async (call) => {
      const handler = answers[asked++];
      if (!handler) throw new Error("no answer scripted");
      const reply = handler(call);
      if (reply instanceof Response) return reply;
      // Stored as the API would: what was said, and how it ended.
      const question = (call.body as { question: string }).question;
      const text = reply.events
        .filter(([name]) => name === "delta")
        .map(([, data]) => (data as { text: string }).text)
        .join("");
      const end = reply.events.find(([name]) => name === "done" || name === "error");
      const status =
        end?.[0] === "done" ? (end[1] as { status: string }).status : end ? "failed" : "stopped";
      const [q, a] = stored(question, {
        id: `a${asked}`,
        text,
        status: status as StoredMessage["status"],
        model: end?.[0] === "done" ? "groq/openai/gpt-oss-120b" : null,
        sources: SOURCES.map((source, i) => ({
          ...source,
          rank: i + 1,
          cited:
            end?.[0] === "done" && (end[1] as { cited: string[] }).cited.includes(source.label),
        })),
      });
      current = conversation([...(current?.messages ?? []), { ...q!, id: `q${asked}` }, a!]);
      return sse(reply.events, { hold: reply.hold, signal: call.request.signal });
    },
    "GET /materials/:id/pages": () =>
      [13, 14].map((n) => ({ page_number: n, title: null, char_count: 200, is_scanned: false })),
    "GET /materials/:id": () => ({ id: MATERIAL, title: "CH09", content_type: "text/markdown" }),
    "GET /materials/:id/pages/:n": ({ params }) => ({
      page_number: Number(params.n),
      title: null,
      char_count: 200,
      is_scanned: false,
      text: `Page ${params.n} about firewalls`,
    }),
  });
  return api;
}

function renderDock({ sessionId = SESSION as string | null } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TutorDock moduleId={MODULE} sessionId={sessionId} topicId={TOPIC} />
    </QueryClientProvider>,
  );
}

const input = () => screen.getByRole("textbox", { name: "Ask about this topic" });

async function ask(user: ReturnType<typeof userEvent.setup>, question: string) {
  await waitFor(() => expect(input()).toBeEnabled());
  await user.type(input(), question);
  await user.keyboard("{Enter}");
}

test("the first question makes the session's conversation and streams the answer", async () => {
  const api = serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "A stateful firewall " }],
        ["delta", { text: "keeps a state table【S2】." }],
        done(),
      ],
    }),
  ]);
  const user = userEvent.setup();
  renderDock();

  await ask(user, "How does stateful inspection work?");

  const turn = await screen.findByRole("article", {
    name: "Question: How does stateful inspection work?",
  });
  await within(turn).findByText(/Answered by gpt-oss-120b \(Groq\)/);
  expect(turn).toHaveTextContent("A stateful firewall keeps a state table");
  expect(
    within(turn).getByText("Answered by gpt-oss-120b (Groq) · first words in 0.6 s (measured)"),
  ).toBeVisible();
  // Cited first and highlighted; the uncited one folded away.
  const cited = within(turn).getByRole("list", { name: "Cited sources" });
  expect(cited).toHaveTextContent("S2CH09 · page 13: Types of firewalls");
  expect(within(turn).getByText("1 more source it was given")).toBeVisible();

  const created = api.calls.find(
    (c) => c.method === "POST" && c.path === `/modules/${MODULE}/tutor/conversations`,
  );
  expect(created?.body).toEqual({ study_session_id: SESSION, topic_id: TOPIC });
  const asked = api.calls.find((c) => c.path === "/conversations/conv-1/messages");
  expect(asked?.body).toEqual({ question: "How does stateful inspection work?", mode: "answer" });
  // Focus is back in the box, ready for the next question.
  expect(input()).toHaveFocus();
  expect(input()).toHaveValue("");
});

test("a citation chip opens the viewer at its page", async () => {
  serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "It keeps a state table [S2]." }],
        done(),
      ],
    }),
  ]);
  const user = userEvent.setup();
  renderDock();
  await ask(user, "Stateful?");

  await user.click(
    await screen.findByRole("button", { name: "Source S2: CH09 · page 13: Types of firewalls" }),
  );

  const viewer = await screen.findByRole("dialog", { name: "CH09" });
  await within(viewer).findByText("Page 13 about firewalls");
  expect(within(viewer).getByRole("button", { name: /^Page 13/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("Stop ends the answer where it is", async () => {
  serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "A stateful firewall" }],
      ],
      hold: true,
    }),
  ]);
  const user = userEvent.setup();
  renderDock();
  await ask(user, "Stateful?");

  await screen.findByText("A stateful firewall");
  await user.click(screen.getByRole("button", { name: "Stop" }));

  expect(await screen.findByText("Stopped.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
});

test("busy providers say when to try again, and Retry asks again", async () => {
  const retryAt = new Date(2026, 10, 19, 14, 5).toISOString();
  const api = serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["error", { message_id: "a1", message: "Trying again after …", retry_at: retryAt }],
      ],
    }),
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "Now it works [S1]." }],
        done({ cited: ["S1"] }),
      ],
    }),
  ]);
  const user = userEvent.setup();
  renderDock();
  await ask(user, "Stateful?");

  const alert = await screen.findByRole("alert");
  const time = new Date(retryAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  expect(alert).toHaveTextContent(`The free AI providers are busy; try again at ${time}.`);
  await user.click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByText(/Now it works/)).toBeVisible();
  const asks = api.calls.filter((c) => c.path === "/conversations/conv-1/messages");
  expect(asks.map((c) => c.body)).toEqual([
    { question: "Stateful?", mode: "answer" },
    { question: "Stateful?", mode: "answer" },
  ]);
});

test("an HTTP error before the stream reads plainly", async () => {
  serve([() => json({ detail: "Conversation not found" }, 404)]);
  const user = userEvent.setup();
  renderDock();
  await ask(user, "Stateful?");

  expect(await screen.findByRole("alert")).toHaveTextContent("Conversation not found");
});

test("a stream that ends without done or error says the connection was lost", async () => {
  serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "Half" }],
      ],
    }),
  ]);
  const user = userEvent.setup();
  renderDock();
  await ask(user, "Stateful?");

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The connection to the tutor was lost before the answer finished.",
  );
});

test("after a reload the session's conversation comes back", async () => {
  const api = serve([], {
    existing: conversation(stored("How does stateful inspection work?")),
  });
  renderDock();

  const turn = await screen.findByRole("article", {
    name: "Question: How does stateful inspection work?",
  });
  await within(turn).findByRole("button", { name: /^Source S2/ });
  expect(turn).toHaveTextContent("It keeps a state table");
  expect(within(turn).getByText(/first words in 0\.6 s \(measured\)/)).toBeVisible();
  const listed = api.calls.find((c) => c.path === `/modules/${MODULE}/tutor/conversations`);
  expect(listed?.method).toBe("GET");
});

test("Shift+Enter adds a line; Enter sends", async () => {
  const api = serve([
    () => ({ events: [["sources", { sources: [] }], ["delta", { text: "Not covered." }], done()] }),
  ]);
  const user = userEvent.setup();
  renderDock();
  await waitFor(() => expect(input()).toBeEnabled());

  await user.type(input(), "Line one{Shift>}{Enter}{/Shift}line two");
  expect(input()).toHaveValue("Line one\nline two");
  await user.keyboard("{Enter}");

  await screen.findByText("Not covered.");
  const asked = api.calls.find((c) => c.path === "/conversations/conv-1/messages");
  expect(asked?.body).toEqual({ question: "Line one\nline two", mode: "answer" });
});

test("an answer saying the material doesn't cover it is just an answer", async () => {
  serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "Your course material doesn't cover this." }],
        done({ cited: [] }),
      ],
    }),
  ]);
  const user = userEvent.setup();
  renderDock();
  await ask(user, "Quantum tunnelling?");

  expect(await screen.findByText("Your course material doesn't cover this.")).toBeVisible();
  await screen.findByText("2 sources it was given (none cited)");
  expect(screen.queryByRole("alert")).toBeNull();
});

test("screen readers hear the answer a sentence at a time", async () => {
  serve([
    () => ({
      events: [
        ["sources", { sources: SOURCES }],
        ["delta", { text: "First sentence. Second sen" }],
      ],
      hold: true,
    }),
  ]);
  const user = userEvent.setup();
  const { container } = renderDock();
  await ask(user, "Stateful?");

  await screen.findByText(/Second sen/);
  const live = container.querySelector('[aria-live="polite"]')!;
  expect(live.textContent).toBe("First sentence.");
  await user.click(screen.getByRole("button", { name: "Stop" }));
});

test("the privacy note shows until the first question", async () => {
  serve([() => ({ events: [["sources", { sources: [] }], ["delta", { text: "Ok." }], done()] })]);
  const user = userEvent.setup();
  renderDock();
  expect(await screen.findByText(PRIVACY_NOTE)).toBeVisible();

  await ask(user, "Stateful?");

  await screen.findByText("Ok.");
  expect(screen.queryByText(PRIVACY_NOTE)).toBeNull();
});

test("until the session reaches the server, the box waits", () => {
  mockApi({});
  renderDock({ sessionId: null });

  expect(input()).toBeDisabled();
  expect(input()).toHaveAttribute("placeholder", "Connecting to the session…");
});

test("on a desktop the panel collapses to one line and opens again", async () => {
  serve([]);
  const user = userEvent.setup();
  renderDock();

  await user.click(screen.getByRole("button", { name: "Collapse the tutor" }));
  expect(screen.queryByRole("textbox")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Ask about this topic…" }));
  expect(input()).toHaveFocus();
});

describe("on a phone", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      (query: string) =>
        ({
          matches: false,
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        }) as unknown as MediaQueryList,
    );
  });

  test("a Tutor button opens the tutor as a bottom sheet", async () => {
    serve([]);
    const user = userEvent.setup();
    renderDock();

    expect(screen.queryByRole("textbox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Tutor" }));

    const sheet = await screen.findByRole("dialog", { name: "Tutor" });
    expect(within(sheet).getByRole("textbox", { name: "Ask about this topic" })).toHaveFocus();
  });
});
