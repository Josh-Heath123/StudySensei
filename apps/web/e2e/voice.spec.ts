import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { uniqueCode } from "./env";

/**
 * Asking by voice in a session, against the real stack, with two stand-ins: the browser's
 * speech (fixtures/fake-speech.js, injected before the app loads: on-device recognition and
 * a local voice) and the answer (page.route fulfils it from the SSE fixture, so no AI is
 * called). The voice-timing PATCH is caught here too: the fixture's message isn't in the
 * database (pytest covers storing it); after the reload, the conversation comes back with
 * the timing that was sent.
 */

const FIXTURES = path.resolve(import.meta.dirname, "fixtures");
const FAKE_SPEECH = path.join(FIXTURES, "fake-speech.js");
const ANSWER_ID = "00000000-0000-4000-8000-000000000002";
const MATERIAL = "00000000-0000-4000-8000-0000000000aa";
const SSE = readFileSync(path.join(FIXTURES, "tutor-answer.sse"), "utf8")
  .replaceAll("{{MATERIAL}}", MATERIAL)
  .replaceAll("{{MESSAGE}}", ANSWER_ID);
const QUESTION = "how do layers differ from pipes and filters";

let sessionToDelete: string | null = null;

test.afterEach(async ({ request }) => {
  if (sessionToDelete) await request.delete(`/api/sessions/${sessionToDelete}`);
  sessionToDelete = null;
});

const spoken = (page: Page) =>
  page.evaluate(
    () =>
      (globalThis as unknown as { __speech: { state: { spoken: string[] } } }).__speech.state
        .spoken,
  );

test("hold to talk: transcript, streamed answer spoken, timing shown and kept after a reload", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000);
  await page.addInitScript({ path: FAKE_SPEECH });
  const module = await (
    await request.post("/api/modules", {
      data: { code: uniqueCode("VOI101", testInfo), name: "Voice e2e" },
    })
  ).json();

  await page.goto("/");
  await page.getByRole("button", { name: "Start session" }).click();
  const dialog = page.getByRole("dialog", { name: "Start a study session" });
  await dialog.getByLabel("Module").selectOption(module.id);
  await dialog.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/session$/);
  sessionToDelete = (await (await request.get("/api/sessions/active")).json()).id;

  await page.route("**/api/conversations/*/messages", (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
      body: SSE,
    }),
  );
  let timing: Record<string, number> | null = null;
  await page.route("**/api/messages/*/voice-timing", async (route) => {
    timing = route.request().postDataJSON() as Record<string, number>;
    await route.fulfill({ json: storedAnswer(timing) });
  });

  const tutor = page.getByRole("complementary", { name: "Tutor" });
  if (!(await tutor.getByRole("textbox").count())) {
    await tutor.getByRole("button", { name: "Ask about this topic…" }).click();
  }
  await expect(tutor.getByRole("textbox", { name: "Ask about this topic" })).toBeEnabled({
    timeout: 20_000,
  });
  const mic = tutor.getByRole("button", { name: "Hold to talk (or hold Space)" });

  // Hold, speak, release.
  await mic.hover();
  await page.mouse.down();
  await expect(tutor.getByRole("status")).toContainText("Listening…");
  await page.evaluate((q) => {
    const speech = (
      globalThis as unknown as { __speech: { hear: (t: string, f: boolean) => void } }
    ).__speech;
    speech.hear(q.slice(0, 14), false);
    speech.hear(q, true);
  }, QUESTION);
  await expect(tutor.getByRole("status")).toContainText(QUESTION);
  await page.mouse.up();

  // The words were sent, never audio; it was recognised on the device.
  const turn = tutor.getByRole("article", { name: `Question: ${QUESTION}` });
  await expect(turn).toContainText("each layer only calls the one below it");
  expect(
    await page.evaluate(
      () =>
        (
          globalThis as unknown as {
            __speech: { state: { recognitions: { startedLocally: boolean }[] } };
          }
        ).__speech.state.recognitions[0]!.startedLocally,
    ),
  ).toBe(true);

  // Spoken a sentence at a time, without Markdown or citation labels.
  await expect.poll(() => spoken(page)).toHaveLength(2);
  const said = await spoken(page);
  expect(said[0]).toBe(
    "A layered style stacks components, so each layer only calls the one below it.",
  );
  expect(said.join(" ")).not.toMatch(/\[S\d\]|【|\*\*|\$/);

  // The latency is stored on the answer and shown beside it.
  await expect(turn).toContainText(/spoken after \d+\.\d s \(measured\)/);
  expect(timing).not.toBeNull();
  const t = timing!;
  expect(t.transcript_ms).toBeLessThanOrEqual(t.first_token_ms!);
  expect(t.first_token_ms).toBeLessThanOrEqual(t.first_sentence_ms!);
  expect(t.first_sentence_ms).toBeLessThanOrEqual(t.voice_latency_ms!);

  // After a reload, the stored answer still says how long it took to be spoken.
  const conversation = (
    await (await request.get(`/api/modules/${module.id}/tutor/conversations`)).json()
  )[0];
  await page.route("**/api/modules/*/tutor/conversations?*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: [{ ...conversation, messages: [storedQuestion(), storedAnswer(t)] }],
    });
  });
  await page.reload();
  const restored = page
    .getByRole("complementary", { name: "Tutor" })
    .getByRole("article", { name: `Question: ${QUESTION}` });
  await expect(restored).toContainText(
    `spoken after ${(t.voice_latency_ms! / 1000).toFixed(1)} s (measured)`,
  );
});

const at = new Date().toISOString();
const base = { mode: "answer", unknown_citations: [], created_at: at };

function storedQuestion() {
  return {
    ...base,
    id: "00000000-0000-4000-8000-000000000001",
    role: "user",
    text: QUESTION,
    status: "complete",
    model: null,
    first_token_ms: null,
    total_ms: null,
    sources: [],
  };
}

function storedAnswer(timing: Record<string, number>) {
  const { voice_latency_ms, ...parts } = timing;
  return {
    ...base,
    id: ANSWER_ID,
    role: "assistant",
    text:
      "A **layered** style stacks components, so each layer only calls the one below it [S1]." +
      " Pipes and filters pass data along a chain of steps【S2】, and the cost is $O(n)$ for $n$ filters.",
    status: "complete",
    model: "groq/openai/gpt-oss-120b",
    first_token_ms: 640,
    total_ms: 1800,
    voice_latency_ms,
    voice_timing: parts,
    sources: [],
  };
}
