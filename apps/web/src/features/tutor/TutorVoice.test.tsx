import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeRecognitionClass, fakeSynth } from "@/test/fakeSpeech";
import { json, mockApi } from "@/test/mockApi";

import type { Conversation, StoredMessage } from "./api";
// Loaded up front: the panel loads it lazily, which on a busy machine can outlast a wait.
import "./AnswerMarkdown";
import { TutorDock } from "./TutorDock";

const SOURCES = [
  { label: "S1", material_id: "mat-1", material_title: "CH03", page_number: 8, page_title: null },
];

function sse(events: [string, unknown][]) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const [name, data] of events) {
        controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
      }
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

const ANSWER = "A **salt** is random data [S1]. It stops rainbow tables.";

function message(id: string, role: "user" | "assistant", text: string): StoredMessage {
  return {
    id,
    role,
    mode: "answer",
    text,
    status: "complete",
    model: role === "assistant" ? "groq/openai/gpt-oss-120b" : null,
    first_token_ms: role === "assistant" ? 600 : null,
    total_ms: role === "assistant" ? 1500 : null,
    unknown_citations: [],
    created_at: "2026-11-19T10:00:00Z",
    sources: [],
  };
}

/** One conversation; each question gets ANSWER, and a PATCH of its timing is stored. */
function serve() {
  let current: Conversation | null = null;
  let asked = 0;
  return mockApi({
    "GET /modules/:moduleId/tutor/conversations": () => (current ? [current] : []),
    "POST /modules/:moduleId/tutor/conversations": () => {
      current = {
        id: "conv-1",
        module_id: "mod-1",
        study_session_id: "sess-1",
        topic_id: null,
        created_at: "2026-11-19T10:00:00Z",
        messages: [],
      };
      return json(current, 201);
    },
    "POST /conversations/:id/messages": ({ body }) => {
      asked += 1;
      const question = (body as { question: string }).question;
      current = {
        ...current!,
        messages: [
          ...current!.messages,
          message(`q${asked}`, "user", question),
          message(`a${asked}`, "assistant", ANSWER),
        ],
      };
      return sse([
        ["sources", { sources: SOURCES }],
        ["delta", { text: "A **salt** is random data [S1]. " }],
        ["delta", { text: "It stops rainbow tables." }],
        [
          "done",
          {
            message_id: `a${asked}`,
            status: "complete",
            model: "groq/openai/gpt-oss-120b",
            first_token_ms: 600,
            total_ms: 1500,
            cited: ["S1"],
            unknown_citations: [],
          },
        ],
      ]);
    },
    "PATCH /messages/:id/voice-timing": ({ params, body }) => {
      const timing = body as Record<string, number>;
      const { voice_latency_ms, ...parts } = timing;
      current = {
        ...current!,
        messages: current!.messages.map((m) =>
          m.id === params.id ? { ...m, voice_latency_ms, voice_timing: parts } : m,
        ),
      };
      return current.messages.find((m) => m.id === params.id)!;
    },
  });
}

/** The browser's speech: on-device recognition in `status`, and a device with a local voice. */
function speech(options: Parameters<typeof fakeRecognitionClass>[0] = {}) {
  const recognition = fakeRecognitionClass(options);
  const synthesis = fakeSynth();
  vi.stubGlobal("SpeechRecognition", recognition.cls);
  vi.stubGlobal("speechSynthesis", synthesis.synth);
  vi.stubGlobal("SpeechSynthesisUtterance", function (text: string) {
    return synthesis.utterance(text);
  });
  return { recognition, synthesis };
}

function renderDock() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TutorDock moduleId="mod-1" sessionId="sess-1" topicId={null} />
    </QueryClientProvider>,
  );
}

const mic = () => screen.findByRole("button", { name: "Hold to talk (or hold Space)" });
const input = () => screen.getByRole("textbox", { name: "Ask about this topic" });

test("hold the mic, speak, release: the transcript is sent and the answer is spoken", async () => {
  const api = serve();
  const { recognition, synthesis } = speech();
  const user = userEvent.setup();
  renderDock();
  await waitFor(() => expect(input()).toBeEnabled());

  await user.pointer({ keys: "[MouseLeft>]", target: await mic() });
  expect(screen.getByRole("status")).toHaveTextContent("Listening…");
  act(() => recognition.last!.hear("what is a salt"));
  expect(screen.getByRole("status")).toHaveTextContent("Listening…what is a salt");
  act(() => recognition.last!.hear("what is a salt for", true));
  await user.pointer({ keys: "[/MouseLeft]", target: await mic() });

  // Sent as typed text would be; audio never leaves (only the words do).
  await waitFor(() =>
    expect(api.calls.find((c) => c.path === "/conversations/conv-1/messages")?.body).toEqual({
      question: "what is a salt for",
      mode: "answer",
    }),
  );
  expect(recognition.last!.startedLocally).toBe(true);
  // Asked by voice, so it's read aloud (Read aloud is off), cleaned and a sentence at a time.
  expect(screen.getByRole("switch", { name: "Read aloud off" })).not.toBeChecked();
  await waitFor(() =>
    expect(synthesis.spoken.map((u) => u.text)).toEqual([
      "A salt is random data.",
      "It stops rainbow tables.",
    ]),
  );
  expect(synthesis.spoken[0]!.voice?.localService).toBe(true);

  act(() => synthesis.startSpeaking(0));

  await waitFor(() =>
    expect(api.calls.find((c) => c.method === "PATCH")?.path).toBe("/messages/a1/voice-timing"),
  );
  const timing = api.calls.find((c) => c.method === "PATCH")!.body as Record<string, number>;
  expect(Object.keys(timing).sort()).toEqual([
    "first_sentence_ms",
    "first_token_ms",
    "transcript_ms",
    "voice_latency_ms",
  ]);
  expect(timing.transcript_ms).toBeLessThanOrEqual(timing.first_token_ms!);
  expect(timing.first_token_ms).toBeLessThanOrEqual(timing.first_sentence_ms!);
  expect(timing.first_sentence_ms).toBeLessThanOrEqual(timing.voice_latency_ms!);
  const turn = screen.getByRole("article", { name: "Question: what is a salt for" });
  await within(turn).findByText(/spoken after \d+\.\d s \(measured\)/);
});

test("hold Space to talk; Space in the question box just types", async () => {
  const api = serve();
  const { recognition } = speech();
  const user = userEvent.setup();
  renderDock();
  await mic();
  await waitFor(() => expect(input()).toBeEnabled());

  await user.type(input(), "a b");
  expect(input()).toHaveValue("a b");
  expect(recognition.started).toEqual([]);

  (document.activeElement as HTMLElement).blur();
  await user.keyboard("[Space>]");
  expect(screen.getByRole("status")).toHaveTextContent("Listening…");
  act(() => recognition.last!.hear("define salting", true));
  await user.keyboard("[/Space]");

  await waitFor(() =>
    expect(api.calls.find((c) => c.path === "/conversations/conv-1/messages")?.body).toEqual({
      question: "define salting",
      mode: "answer",
    }),
  );
});

test("Space on a focused button presses it rather than talking", async () => {
  serve();
  const { recognition } = speech();
  const user = userEvent.setup();
  renderDock();
  await mic();

  screen.getByRole("switch", { name: "Read aloud off" }).focus();
  await user.keyboard(" ");

  expect(recognition.started).toEqual([]);
  expect(screen.getByRole("switch", { name: "Read aloud on" })).toBeChecked();
});

test("Escape cancels: nothing is sent", async () => {
  const api = serve();
  const { recognition } = speech();
  const user = userEvent.setup();
  renderDock();
  await waitFor(() => expect(input()).toBeEnabled());

  await user.pointer({ keys: "[MouseLeft>]", target: await mic() });
  act(() => recognition.last!.hear("never mind", true));
  await user.keyboard("{Escape}");
  await user.pointer({ keys: "[/MouseLeft]", target: await mic() });

  expect(recognition.last!.aborted).toBe(true);
  expect(screen.queryByRole("status")).toBeNull();
  expect(api.calls.some((c) => c.path === "/conversations/conv-1/messages")).toBe(false);
});

test("Read aloud is off by default, reads typed answers when on, and is remembered", async () => {
  serve();
  const { synthesis } = speech();
  const user = userEvent.setup();
  const { unmount } = renderDock();
  await waitFor(() => expect(input()).toBeEnabled());

  await user.type(input(), "What is a salt?{Enter}");
  await screen.findByText(/Answered by/);
  expect(synthesis.spoken).toEqual([]); // typed, and Read aloud is off

  await user.click(screen.getByRole("switch", { name: "Read aloud off" }));
  await user.type(input(), "And a pepper?{Enter}");
  await waitFor(() => expect(synthesis.spoken).toHaveLength(2));
  // Typed, so nothing is timed.
  act(() => synthesis.startSpeaking(0));
  unmount();
  expect(synthesis.synth.cancel).toHaveBeenCalled(); // leaving the session stops it

  renderDock();
  expect(await screen.findByRole("switch", { name: "Read aloud on" })).toBeChecked();
});

test("Stop reading, and push-to-talk, both silence the answer", async () => {
  serve();
  const { synthesis } = speech();
  localStorage.setItem("studysensei.tutor.read-aloud", "1");
  const user = userEvent.setup();
  renderDock();
  await waitFor(() => expect(input()).toBeEnabled());

  await user.type(input(), "What is a salt?{Enter}");
  await waitFor(() => expect(synthesis.spoken).toHaveLength(2));
  act(() => synthesis.startSpeaking(0));
  await user.click(await screen.findByRole("button", { name: "Stop reading" }));
  expect(synthesis.synth.cancel).toHaveBeenCalledTimes(1);

  await user.type(input(), "And a pepper?{Enter}");
  await waitFor(() => expect(synthesis.spoken).toHaveLength(4));
  await user.pointer({ keys: "[MouseLeft>]", target: await mic() });
  expect(synthesis.synth.cancel).toHaveBeenCalledTimes(2);
  // The silenced answer isn't started again.
  expect(synthesis.spoken).toHaveLength(4);
});

test("a downloadable speech pack: set up voice, then the mic appears", async () => {
  serve();
  const { recognition } = speech({ status: "downloadable" });
  const user = userEvent.setup();
  renderDock();

  await user.click(
    await screen.findByRole("button", {
      name: "Set up voice (downloads a speech pack to this device)",
    }),
  );

  expect(recognition.cls.install).toHaveBeenCalledWith({
    langs: [expect.any(String)],
    processLocally: true,
  });
  expect(await mic()).toBeVisible();
});

test("a failed speech-pack download can be tried again", async () => {
  serve();
  speech({ status: "downloadable", installs: false });
  const user = userEvent.setup();
  renderDock();

  await user.click(await screen.findByRole("button", { name: /Set up voice/ }));

  expect(await screen.findByText("The speech pack didn't download.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  expect(screen.queryByRole("button", { name: /Hold to talk/ })).toBeNull();
});

test.each([
  ["a browser without on-device recognition", { onDevice: false }],
  ["no speech pack for this language", { status: "unavailable" }],
])("%s: no mic, one line, typing works", async (_, options) => {
  serve();
  const { recognition } = speech(options);
  renderDock();

  expect(
    await screen.findByText(
      "This browser can't recognise speech on the device, so voice is off. Typing works.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: /Hold to talk/ })).toBeNull();
  expect(recognition.started).toEqual([]);
});

test("no local voice: no Read aloud, and one line saying so", async () => {
  serve();
  speech();
  vi.stubGlobal("speechSynthesis", fakeSynth([]).synth);
  renderDock();

  expect(
    await screen.findByText("This device has no voice of its own to read answers."),
  ).toBeVisible();
  expect(screen.queryByRole("switch")).toBeNull();
});
