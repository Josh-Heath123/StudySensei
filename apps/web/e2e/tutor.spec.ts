import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "./base";

import { uniqueCode } from "./env";
import { startWorker, stopWorker } from "./worker";

/**
 * The tutor panel in a running session, against the real stack, except the answers:
 * page.route fulfils the streamed answer (and, after the reload, the stored conversation)
 * from a fixture, so no AI is called and nothing fake lives in the app.
 */

const FIXTURE = readFileSync(
  path.resolve(import.meta.dirname, "fixtures/tutor-answer.sse"),
  "utf8",
);
const QUESTION = "How do layers differ from pipes and filters?";

let sessionToDelete: string | null = null;

test.afterEach(async ({ request }) => {
  stopWorker();
  // One open session per user: leave none behind for the next spec.
  if (sessionToDelete) await request.delete(`/api/sessions/${sessionToDelete}`);
  sessionToDelete = null;
});

/** A module with a topic and the synthetic 3-page lecture, extracted by the real worker. */
async function setUp(request: APIRequestContext, code: string) {
  const module = await (
    await request.post("/api/modules", { data: { code, name: "Tutor e2e" } })
  ).json();
  const topic = await (
    await request.post(`/api/modules/${module.id}/topics`, {
      data: { name: "Architectural styles" },
    })
  ).json();
  const upload = await request.post(`/api/modules/${module.id}/materials`, {
    multipart: {
      file: {
        name: "lecture.pdf",
        mimeType: "application/pdf",
        buffer: readFileSync(
          path.resolve(import.meta.dirname, "../../api/tests/fixtures/lecture.pdf"),
        ),
      },
      kind: "slides",
      allow_ai: "true",
    },
  });
  expect(upload.status()).toBe(201);
  const material = await upload.json();
  startWorker();
  await expect
    .poll(async () => (await (await request.get(`/api/materials/${material.id}`)).json()).status, {
      timeout: 150_000,
    })
    .toBe("ready");
  return { module, topic, material };
}

async function startSession(page: Page, moduleId: string, topicId: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Start session" }).click();
  const dialog = page.getByRole("dialog", { name: "Start a study session" });
  await dialog.getByLabel("Module").selectOption(moduleId);
  await dialog.getByLabel("Topic (optional)").selectOption(topicId);
  await dialog.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/session$/);
}

function fixtureAnswer(materialId: string) {
  return FIXTURE.replaceAll("{{MATERIAL}}", materialId).replaceAll(
    "{{MESSAGE}}",
    "00000000-0000-4000-8000-000000000002",
  );
}

/** The conversation as the API would have stored it after the fixture's answer. */
function storedConversation(conversation: Record<string, unknown>, materialId: string) {
  const at = new Date().toISOString();
  const source = (label: string, page: number, cited: boolean) => ({
    label,
    rank: Number(label.slice(1)),
    material_id: materialId,
    material_title: "lecture",
    page_number: page,
    page_title: null,
    cited,
  });
  const base = { mode: "answer", unknown_citations: [], created_at: at };
  return {
    ...conversation,
    messages: [
      {
        ...base,
        id: "00000000-0000-4000-8000-000000000001",
        role: "user",
        text: QUESTION,
        status: "complete",
        model: null,
        first_token_ms: null,
        total_ms: null,
        sources: [],
      },
      {
        ...base,
        id: "00000000-0000-4000-8000-000000000002",
        role: "assistant",
        text:
          "A **layered** style stacks components, so each layer only calls the one below it [S1]." +
          " Pipes and filters pass data along a chain of steps【S2】.",
        status: "complete",
        model: "groq/openai/gpt-oss-120b",
        first_token_ms: 640,
        total_ms: 1800,
        sources: [source("S1", 1, true), source("S2", 3, true)],
      },
    ],
  };
}

test("ask the tutor in a session: streamed answer, a citation into the viewer, Stop, reload, phone", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(240_000);
  const { module, topic, material } = await setUp(request, uniqueCode("TUT101", testInfo));
  await startSession(page, module.id, topic.id);
  const active = await (await request.get("/api/sessions/active")).json();
  sessionToDelete = active.id;

  // The answer streams from the fixture.
  let answers = 0;
  await page.route("**/api/conversations/*/messages", async (route) => {
    answers += 1;
    if (answers === 1) {
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: fixtureAnswer(material.id),
      });
      return;
    }
    // The second answer never finishes: the student stops it. Hold the request open.
    await new Promise(() => undefined);
  });

  const tutor = page.getByRole("complementary", { name: "Tutor" });
  const box = tutor.getByRole("textbox", { name: "Ask about this topic" });
  await expect(box).toBeEnabled({ timeout: 20_000 });
  await expect(tutor).toContainText("Your question and the matching pages of your material");
  await box.fill(QUESTION);
  await box.press("Enter");

  const turn = tutor.getByRole("article", { name: `Question: ${QUESTION}` });
  await expect(turn).toContainText("each layer only calls the one below it");
  await expect(turn.locator("strong")).toHaveText("layered");
  await expect(turn.locator(".katex").first()).toBeVisible();
  await expect(turn).toContainText(
    "Answered by gpt-oss-120b (Groq) · first words in 0.6 s (measured)",
  );
  await expect(box).toBeFocused();

  // The conversation is the session's, on its topic.
  const conversations = await (
    await request.get(`/api/modules/${module.id}/tutor/conversations`, {
      params: { study_session_id: active.id },
    })
  ).json();
  expect(conversations).toHaveLength(1);
  expect(conversations[0]).toMatchObject({ study_session_id: active.id, topic_id: topic.id });

  // [S2] (written 【S2】) opens the viewer at its page.
  await turn.getByRole("button", { name: "Source S2: lecture · page 3" }).click();
  const viewer = page.getByRole("dialog", { name: "lecture" });
  await expect(viewer.getByText("Page 3 of 3")).toBeVisible();
  await expect(viewer.getByRole("button", { name: /^Page 3/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await page.keyboard.press("Escape");
  await expect(viewer).toHaveCount(0);

  // Stop an answer that's still coming.
  await box.fill("And which is easier to test?");
  await box.press("Enter");
  await tutor.getByRole("button", { name: "Stop" }).click();
  await expect(tutor.getByText("Stopped.")).toBeVisible();
  await expect(tutor.getByRole("button", { name: "Send" })).toBeVisible();

  // After a reload, the session's conversation comes back (as the API stored it).
  await page.route("**/api/modules/*/tutor/conversations?*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ json: [storedConversation(conversations[0], material.id)] });
  });
  await page.reload();
  const restored = page
    .getByRole("complementary", { name: "Tutor" })
    .getByRole("article", { name: `Question: ${QUESTION}` });
  await expect(restored).toContainText("Pipes and filters pass data along a chain of steps");
  await expect(restored.getByRole("list", { name: "Cited sources" })).toContainText(
    "lecture · page 3",
  );

  // On a phone, the tutor is a bottom sheet.
  await page.setViewportSize({ width: 375, height: 800 });
  await expect(page.getByRole("complementary", { name: "Tutor" })).toHaveCount(0);
  await page.getByRole("button", { name: "Tutor", exact: true }).click();
  const sheet = page.getByRole("dialog", { name: "Tutor" });
  await expect(sheet.getByRole("article", { name: `Question: ${QUESTION}` })).toBeVisible();
  await expect(sheet.getByRole("textbox", { name: "Ask about this topic" })).toBeFocused();
});
