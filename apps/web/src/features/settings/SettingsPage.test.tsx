import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import type { AiPingResult, AiStatus } from "./api";
import { formatReset } from "./aiSettings";

const RESET = "2026-11-19T08:00:00Z";

function aStatus(usedFlash = 5): AiStatus {
  return {
    available: true,
    providers: [
      { name: "gemini", configured: true, key_set: true },
      { name: "groq", configured: false, key_set: false },
      { name: "ollama", configured: false, key_set: false },
    ],
    roles: {
      smart: ["gemini/gemini-3.8-flash", "groq/openai/gpt-oss-120b"],
      bulk: ["gemini/gemini-3.5-flash-lite"],
      vision: ["gemini/gemini-3.5-flash-lite"],
      long: ["gemini/gemini-3.5-flash-lite", "groq/openai/gpt-oss-120b"],
    },
    models: [
      {
        provider: "gemini",
        model: "gemini-3.8-flash",
        configured: true,
        vision: false,
        daily_budget: 18,
        used_today: usedFlash,
        resets_at: RESET,
      },
      {
        provider: "groq",
        model: "openai/gpt-oss-120b",
        configured: false,
        vision: false,
        daily_budget: 900,
        used_today: 0,
        resets_at: RESET,
      },
      {
        provider: "gemini",
        model: "gemini-3.5-flash-lite",
        configured: true,
        vision: true,
        daily_budget: 450,
        used_today: 12,
        resets_at: RESET,
      },
    ],
  };
}

function aResult(changes: Partial<AiPingResult>): AiPingResult {
  return {
    provider: "gemini",
    model: "gemini-3.8-flash",
    status: "ok",
    latency_ms: 812,
    error: null,
    resets_at: null,
    in_models_list: true,
    models_list_error: null,
    ...changes,
  };
}

test("says which providers have a key without showing one, and how to add one", async () => {
  mockApi({ "GET /ai/status": () => aStatus() });
  renderApp("/settings");

  expect(await screen.findByLabelText("Gemini: Key set")).toBeInTheDocument();
  expect(screen.getByLabelText("Groq: No key")).toBeInTheDocument();
  expect(screen.getByLabelText("Ollama: No model")).toBeInTheDocument();
  expect(screen.getByText("apps/api/.env")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "AI providers" })).toBeInTheDocument();
});

test("lists each role's models in order with what uses it", async () => {
  mockApi({ "GET /ai/status": () => aStatus() });
  renderApp("/settings");

  const smart = await screen.findByRole("list", { name: "smart models" });
  expect(
    within(smart)
      .getAllByRole("listitem")
      .map((li) => li.textContent),
  ).toEqual(["gemini/gemini-3.8-flash", "→groq/openai/gpt-oss-120b"]);
  expect(screen.getByText(": The tutor")).toBeInTheDocument();
  expect(screen.getByText(": Tagging")).toBeInTheDocument();
  expect(screen.getByText(": Images")).toBeInTheDocument();
  expect(screen.getByText(": Whole documents and topic maps")).toBeInTheDocument();
});

test("meters today's usage: the count measured, the budget estimated, the reset local", async () => {
  mockApi({ "GET /ai/status": () => aStatus(18) });
  renderApp("/settings");

  const meter = await screen.findByRole("meter", {
    name: "gemini/gemini-3.8-flash requests today",
  });
  expect(meter).toHaveAttribute("aria-valuenow", "18");
  expect(meter).toHaveAttribute("aria-valuemax", "18");
  const row = meter.closest("li")!;
  expect(row).toHaveTextContent("18 requests today (Measured)");
  expect(row).toHaveTextContent("budget about 18 a day (Estimated)");
  expect(row).toHaveTextContent("Used up");
  expect(row).toHaveTextContent(`resets ${formatReset(RESET)}`);
  expect(
    screen.getByRole("meter", { name: "gemini/gemini-3.5-flash-lite requests today" }),
  ).toHaveAttribute("aria-valuenow", "12");
});

test("tests the keys: one request per model, disabled while running, then refetches usage", async () => {
  let release!: () => void;
  const done = new Promise<void>((resolve) => (release = resolve));
  const { calls } = mockApi({
    "GET /ai/status": () => aStatus(),
    "POST /ai/ping": async () => {
      await done;
      return {
        results: [
          aResult({}),
          aResult({
            model: "gemini-3.5-flash-lite",
            status: "failed",
            latency_ms: 300,
            error: "gemini: HTTP 400: API key not valid",
          }),
        ],
      };
    },
  });
  renderApp("/settings");
  const user = userEvent.setup();

  expect(
    await screen.findByText(/one short request to each configured model \(2 requests\)/),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Test keys" }));

  expect(screen.getByRole("button", { name: "Testing…" })).toBeDisabled();
  release();

  const results = await screen.findByRole("list", { name: "Test results" });
  const ok = within(results).getByRole("listitem", { name: "gemini/gemini-3.8-flash" });
  expect(ok).toHaveTextContent("OK");
  expect(ok).toHaveTextContent("812 ms");
  const failed = within(results).getByRole("listitem", { name: "gemini/gemini-3.5-flash-lite" });
  expect(failed).toHaveTextContent("Failed");
  expect(failed).toHaveTextContent("gemini: HTTP 400: API key not valid");
  expect(screen.getByRole("button", { name: "Test keys" })).toBeEnabled();
  await waitFor(() =>
    expect(calls.filter((c) => c.method === "GET" && c.path === "/ai/status")).toHaveLength(2),
  );
  expect(calls.filter((c) => c.path === "/ai/ping")).toHaveLength(1);
});

test("shows a skipped model's reset time and a model missing from the provider's list", async () => {
  mockApi({
    "GET /ai/status": () => aStatus(18),
    "POST /ai/ping": () => ({
      results: [
        aResult({ status: "skipped", latency_ms: null, resets_at: RESET }),
        aResult({ model: "gemini-3.5-flash-lite", in_models_list: false }),
      ],
    }),
  });
  renderApp("/settings");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Test keys" }));

  const skipped = await screen.findByRole("listitem", { name: "gemini/gemini-3.8-flash" });
  expect(skipped).toHaveTextContent("Skipped");
  expect(skipped).toHaveTextContent(`Budget used up until ${formatReset(RESET)}`);
  const unlisted = screen.getByRole("listitem", { name: "gemini/gemini-3.5-flash-lite" });
  expect(unlisted).toHaveTextContent("Not in the provider's model list");
});

test("with no provider set up, the test button is disabled", async () => {
  mockApi({
    "GET /ai/status": () => ({
      ...aStatus(),
      available: false,
      providers: aStatus().providers.map((p) => ({ ...p, configured: false, key_set: false })),
      models: aStatus().models.map((m) => ({ ...m, configured: false })),
    }),
  });
  renderApp("/settings");

  expect(await screen.findByRole("button", { name: "Test keys" })).toBeDisabled();
  expect(screen.getByText(/Add a key first/)).toBeInTheDocument();
  expect(screen.getByLabelText("Gemini: No key")).toBeInTheDocument();
});

test("the privacy note says what is and isn't sent", async () => {
  mockApi({ "GET /ai/status": () => aStatus() });
  renderApp("/settings");

  expect(await screen.findByText(/may use prompts to improve their models/)).toBeInTheDocument();
  expect(
    screen.getByText("Materials with Allow AI turned off are never sent."),
  ).toBeInTheDocument();
});

describe("appearance", () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme;
  });

  test("defaults to System", async () => {
    mockApi({ "GET /ai/status": () => aStatus() });
    renderApp("/settings");

    const group = await screen.findByRole("radiogroup", { name: "Appearance" });
    expect(within(group).getByRole("radio", { name: "System" })).toBeChecked();
    expect(within(group).getByRole("radio", { name: "Light" })).not.toBeChecked();
    expect(within(group).getByRole("radio", { name: "Dark" })).not.toBeChecked();
    expect(screen.getByText("System follows your device's light or dark setting.")).toBeVisible();
  });

  test("choosing Dark applies and stores it; choosing System forgets it", async () => {
    mockApi({ "GET /ai/status": () => aStatus() });
    renderApp("/settings");
    const user = userEvent.setup();
    const group = await screen.findByRole("radiogroup", { name: "Appearance" });

    await user.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(within(group).getByRole("radio", { name: "Dark" })).toBeChecked();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("studysensei.appearance")).toBe("dark");

    await user.click(within(group).getByRole("radio", { name: "System" }));
    expect(within(group).getByRole("radio", { name: "System" })).toBeChecked();
    expect(localStorage.getItem("studysensei.appearance")).toBeNull();
  });

  test("starts from the stored choice", async () => {
    localStorage.setItem("studysensei.appearance", "light");
    mockApi({ "GET /ai/status": () => aStatus() });
    renderApp("/settings");

    const group = await screen.findByRole("radiogroup", { name: "Appearance" });
    expect(within(group).getByRole("radio", { name: "Light" })).toBeChecked();
  });
});
