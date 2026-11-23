// `npm run screenshots`: the README's screenshots of the real app, with synthetic demo data,
// in light and dark (docs/assets/screenshots/<name>-<light|dark>.png).
//
// Like scripts/e2e.mjs it uses its own database (studysensei_demo, rebuilt each run), ports
// (API :8002, web :5176) and storage folder (data/demo-materials), so it never touches the dev
// stack. It seeds the demo (apps/api/scripts/demo_seed.py: original text, the real extraction
// and indexing pipeline, no AI keys), takes the shots with Playwright at 1440×900 and device
// scale 2 with the date fixed, frames each with a soft hairline, and stops everything it started.
//
// `npm run screenshots -- --qa <folder>` also captures every screen (and the main dialogs) in
// both themes at 1440, 768 and 375 px wide into <folder>, for reviewing a visual change. Keep
// that folder outside the repository.
import { execSync, spawn, spawnSync } from "node:child_process";
import { mkdirSync, rmSync, statSync } from "node:fs";
import path from "node:path";

import { chromium } from "@playwright/test";

const root = path.resolve(import.meta.dirname, "..");
const outDir = path.join(root, "docs", "assets", "screenshots");
const DB = "studysensei_demo";
const API_PORT = 8002;
const WEB_PORT = 5176;
const DATABASE_URL = `postgresql+asyncpg://studysensei:studysensei@localhost:5433/${DB}`;
const STORAGE_DIR = path.join(root, "data", "demo-materials");
// The demo's "now": a Thursday evening, 20 minutes into a planned block, with three days of
// plan history behind it. Sessions, deadlines and tasks are seeded around it. The API, the
// worker and the seed run with FAKE_NOW set to it (decision 0023), and the browser's clock
// is fixed to the same instant, so both sides agree on the date.
const NOW = "2026-11-19T18:20:00+02:00";
const TIMEZONE = "Africa/Johannesburg";
const VIEWPORT = { width: 1440, height: 900 };

// No AI: blank keys beat apps/api/.env (blank means unset), so nothing can call a provider.
const env = {
  ...process.env,
  DATABASE_URL,
  STORAGE_DIR,
  GEMINI_API_KEY: "",
  GROQ_API_KEY: "",
  OLLAMA_MODEL: "",
  FAKE_NOW: NOW,
  // The private calendar link points at this web app.
  PUBLIC_URL: `http://localhost:${WEB_PORT}`,
  // No push from the demo, whatever apps/api/.env holds.
  VAPID_PUBLIC_KEY: "",
  VAPID_PRIVATE_KEY: "",
};
const run = (cmd, extra = {}) =>
  execSync(cmd, { cwd: root, stdio: "inherit", env: { ...env, ...extra } });
const children = [];

function stopAll() {
  for (const child of children.splice(0)) {
    if (child.pid === undefined) continue;
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
      });
    } else {
      try {
        process.kill(-child.pid, "SIGTERM");
      } catch {
        // Already gone.
      }
    }
  }
}

function start(name, cmd, cwd, extra = {}) {
  const child = spawn(cmd, {
    cwd,
    shell: true,
    detached: process.platform !== "win32",
    env: { ...env, ...extra },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout.on("data", (chunk) => (output += chunk));
  child.stderr.on("data", (chunk) => (output += chunk));
  child.on("exit", (code) => {
    if (code && children.includes(child))
      console.error(`${name} exited (${code}):\n${output}`);
  });
  children.push(child);
}

async function waitFor(url, label) {
  for (let i = 0; i < 120; i += 1) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      // Not up yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`${label} didn't answer at ${url}`);
}

const FRAME = {
  light: { border: "#d9d9e0", canvas: "#f0f0f0" },
  dark: { border: "#2c2c3a", canvas: "#0b0b12" },
};

/** Re-render a screenshot inside a soft hairline frame with rounded corners, at the same density. */
async function frame(browser, png, file, theme) {
  // A PNG's width and height are big-endian at bytes 16 and 20; CSS pixels are half (scale 2).
  const width = png.readUInt32BE(16) / 2;
  const height = png.readUInt32BE(20) / 2;
  const page = await browser.newPage({
    viewport: { width: width + 2, height: height + 2 },
    deviceScaleFactor: 2,
  });
  const src = `data:image/png;base64,${png.toString("base64")}`;
  const { border, canvas } = FRAME[theme];
  await page.setContent(
    `<body style="margin:0;background:transparent"><div id="f" style="border:1px solid ${border};` +
      `border-radius:16px;overflow:hidden;background:${canvas};width:${width}px;height:${height}px">` +
      `<img src="${src}" style="display:block;width:100%;height:100%"></div></body>`,
  );
  await page
    .locator("#f")
    .screenshot({ path: path.join(outDir, file), omitBackground: true });
  await page.close();
  const kb = Math.round(statSync(path.join(outDir, file)).size / 1024);
  console.log(`  ${file}: ${kb} KB`);
}

/** A browser context in one theme: the app reads the same Appearance key the Settings page sets. */
async function context(browser, theme, viewport = VIEWPORT, scale = 2) {
  const ctx = await browser.newContext({
    baseURL: `http://localhost:${WEB_PORT}`,
    viewport,
    deviceScaleFactor: scale,
    locale: "en-GB",
    timezoneId: TIMEZONE,
    colorScheme: theme,
  });
  // On-device speech and a local voice, faked as in e2e/voice.spec.ts: the tutor shows its
  // mic and Read aloud, and headless Chromium never reaches its real SpeechRecognition
  // (which crashes the page).
  await ctx.addInitScript({
    path: path.join(root, "apps/web/e2e/fixtures/fake-speech.js"),
  });
  await ctx.addInitScript((value) => {
    try {
      localStorage.setItem("studysensei.appearance", value);
    } catch {
      // Storage blocked: the colour scheme above still picks the theme.
    }
  }, theme);
  return ctx;
}

/** Wait for fonts and any transitions to settle before a shot. */
async function settle(page, ms = 600) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(ms);
}

async function main() {
  console.log("Starting Postgres and rebuilding the demo database…");
  run("docker compose up -d --wait db");
  const exists = execSync(
    `docker compose exec -T db psql -U studysensei -d studysensei -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB}'"`,
    { cwd: root },
  )
    .toString()
    .trim();
  if (exists !== "1") {
    run(
      `docker compose exec -T db psql -U studysensei -d studysensei -c "CREATE DATABASE ${DB}"`,
    );
  }
  rmSync(STORAGE_DIR, { recursive: true, force: true });
  run("uv run --directory apps/api alembic downgrade base");
  run("uv run --directory apps/api alembic upgrade head");
  run("uv run --directory apps/api python -m app.seed");
  run(`uv run --directory apps/api python -m scripts.demo_seed --now ${NOW}`);

  // A throwaway VAPID pair, so Settings shows Reminders as set up on the server. Only the
  // API gets it: the worker keeps push off, so nothing is ever sent from the demo.
  const vapid = Object.fromEntries(
    execSync("uv run --directory apps/api python -m app.push.keys", {
      cwd: root,
    })
      .toString()
      .split(/\r?\n/)
      .filter((line) => line.startsWith("VAPID_"))
      .map((line) => line.split(/=(.*)/s).slice(0, 2)),
  );

  console.log("Starting the API and the web app on their own ports…");
  start(
    "API",
    `uv run uvicorn app.main:app --port ${API_PORT}`,
    path.join(root, "apps", "api"),
    vapid,
  );
  start(
    "worker",
    "uv run python -m app.jobs.worker",
    path.join(root, "apps", "api"),
    { PRELOAD_EMBEDDER: "false" },
  );
  start(
    "web",
    `npx vite --port ${WEB_PORT} --strictPort`,
    path.join(root, "apps", "web"),
    {
      API_PROXY_TARGET: `http://localhost:${API_PORT}`,
    },
  );
  await waitFor(`http://localhost:${API_PORT}/health`, "The API");
  await waitFor(`http://localhost:${WEB_PORT}`, "The web app");

  const modules = await (
    await fetch(`http://localhost:${API_PORT}/modules`)
  ).json();
  const module = modules.find((item) => item.code === "NET201");
  if (!module) throw new Error("The demo module NET201 wasn't seeded");

  mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const fixed = new Date(NOW).getTime();
  try {
    for (const theme of ["light", "dark"]) {
      console.log(`${theme}:`);
      // Today, Topics and the viewer: the date is fixed, timers run (pdf.js needs them).
      const ctx = await context(browser, theme);
      const page = await ctx.newPage();
      await page.clock.setFixedTime(fixed);

      await page.goto("/");
      await page.getByText("Semester test 2").first().waitFor();
      await page.getByLabel("Database: Connected").waitFor();
      await settle(page);
      // The whole page, so the deadlines under the day timeline are in it too.
      await frame(
        browser,
        await page.screenshot({ fullPage: true }),
        `today-${theme}.png`,
        theme,
      );

      await page.goto(`/modules/${module.id}?tab=topics`);
      await page
        .getByRole("button", { name: /Slow start and ssthresh/ })
        .first()
        .click();
      const pages = page.getByRole("dialog");
      await pages.waitFor();
      await pages
        .getByText(/Week 6 slides/)
        .first()
        .waitFor();
      await settle(page);
      await frame(
        browser,
        await page.screenshot(),
        `topics-${theme}.png`,
        theme,
      );
      await page.keyboard.press("Escape");

      await page.goto(`/modules/${module.id}?tab=materials`);
      await page
        .getByRole("searchbox", { name: "Search materials" })
        .fill("slow start threshold");
      await page.getByRole("button", { name: "Search", exact: true }).click();
      const results = page.getByRole("list", {
        name: "Results for “slow start threshold”",
      });
      const hit = results.getByRole("button").first();
      await hit.waitFor();
      console.log(
        `  first search result: ${(await hit.innerText()).split("\n")[0]}`,
      );
      await hit.click();
      const viewer = page.getByRole("dialog", { name: "Week 6 slides" });
      await viewer.getByText(/Page \d+ of 6/).waitFor();
      await viewer.locator("canvas").first().waitFor();
      await settle(page, 2000); // pdf.js draws the page
      await frame(
        browser,
        await page.screenshot(),
        `viewer-${theme}.png`,
        theme,
      );
      await ctx.close();

      // The running session the demo seed opened 18 minutes before "now", with the tutor
      // panel open on its one exchange. The clock runs until the panel has loaded (the data
      // layer delivers results through timers), then the time is fixed: the timer shows 32:00.
      const sessionCtx = await context(browser, theme);
      const sessionPage = await sessionCtx.newPage();
      await sessionPage.clock.install({ time: fixed });
      await sessionPage.goto("/session");
      const tutor = sessionPage.getByRole("complementary", { name: "Tutor" });
      await tutor.locator(".katex").first().waitFor();
      await tutor.getByText(/first words in 0\.6 s/).waitFor();
      await sessionPage.clock.setFixedTime(fixed + 1000);
      await sessionPage
        .getByRole("timer")
        .filter({ hasText: "32:00" })
        .waitFor();
      // The panel opens on its newest turn (the quiz): show the answer for this one.
      const log = tutor.getByRole("log", { name: "Tutor conversation" });
      await log.evaluate((box) => (box.scrollTop = 0));
      await settle(sessionPage, 400);
      await frame(
        browser,
        await sessionPage.screenshot(),
        `session-${theme}.png`,
        theme,
      );

      // The quiz: question 1 answered (right), its explanation and citation showing.
      const quiz = tutor.getByRole("region", { name: "Quiz" });
      await quiz.scrollIntoViewIfNeeded();
      await quiz
        .getByRole("button", { name: /^B\. It doubles every round trip/ })
        .click();
      await quiz.getByText("Right.").waitFor();
      await quiz.locator(".answer-prose button").first().waitFor();
      // The quiz from its first line ("Question 1 of 3") at the top of the box.
      await quiz.evaluate((element) => {
        const box = element.closest('[role="log"]');
        box.scrollTop +=
          element.getBoundingClientRect().top -
          box.getBoundingClientRect().top -
          16;
      });
      await settle(sessionPage, 400);
      await frame(
        browser,
        await sessionPage.screenshot(),
        `quiz-${theme}.png`,
        theme,
      );
      // Undo the pick, so the other theme's shot starts from the same question.
      const [conversation] = await (
        await sessionPage.request.get(
          `/api/modules/${module.id}/tutor/conversations`,
        )
      ).json();
      const quizMessage = conversation.messages.find(
        (m) => m.mode === "quiz" && m.quiz,
      );
      await sessionPage.request.patch(
        `/api/messages/${quizMessage.id}/quiz-answers`,
        {
          data: { answers: [null, null, null] },
        },
      );
      await sessionCtx.close();
    }

    const qa = process.argv.indexOf("--qa");
    if (qa !== -1)
      await review(browser, process.argv[qa + 1], module.id, fixed);
  } finally {
    await browser.close();
  }
}

// Init scripts for the Reminders card's states: notifications allowed with this browser
// already subscribed (the card saves the subscription, finding "This device"), and blocked.
const REMINDER_STATES = {
  on: `(() => {
    Object.defineProperty(Notification, "permission", { get: () => "granted" });
    const sub = {
      endpoint: "https://push.example/qa-this-browser",
      toJSON: () => ({ endpoint: "https://push.example/qa-this-browser", keys: { p256dh: "BQA", auth: "QA" } }),
      unsubscribe: async () => true,
    };
    navigator.serviceWorker.getRegistration = async () => ({ pushManager: { getSubscription: async () => sub } });
  })()`,
  denied: `Object.defineProperty(Notification, "permission", { get: () => "denied" });`,
};

/** The AI's check of the demo's short answer, for the QA screenshots (no AI in the demo). */
const QA_MARKING = {
  coverage: [
    {
      index: 1,
      key_point: "ssthresh marks a window size that was safe",
      covered: false,
    },
    { index: 2, key_point: "Past it, growth becomes additive", covered: true },
    {
      index: 3,
      key_point: "This avoids overflowing router queues",
      covered: false,
    },
  ],
  verdict: "incorrect",
  suggested_grade: 1,
  feedback:
    "You describe the additive growth past ssthresh; say what ssthresh marks and why growth slows there.",
  model: "groq/openai/gpt-oss-120b",
};

/** Every screen and the main dialogs, in both themes, at three widths (full page, scale 1). */
async function review(browser, dir, moduleId, fixed) {
  if (!dir) throw new Error("--qa needs a folder");
  mkdirSync(dir, { recursive: true });
  // Another device with reminders on, for the card's "Other devices".
  await fetch(`http://localhost:${API_PORT}/push/subscriptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: "https://push.example/qa-phone",
      keys: { p256dh: "BPhone", auth: "Phone" },
      label: "Chrome on Android",
    }),
  });
  const tabs = ["assessments", "tasks", "sessions", "topics", "materials"];
  const screens = [
    ["today", "/"],
    ["modules", "/modules"],
    ...tabs.map((tab) => [`module-${tab}`, `/modules/${moduleId}?tab=${tab}`]),
    ["plan", "/plan"],
    ["practice", "/practice"],
    ["practice-items", "/practice/items"],
    ["insights", "/insights"],
    ["settings", "/settings"],
    ["session", "/session"],
  ];
  const shots = [];
  for (const theme of ["light", "dark"]) {
    for (const width of [1440, 768, 375]) {
      const ctx = await context(browser, theme, { width, height: 900 }, 1);
      const page = await ctx.newPage();
      await page.clock.setFixedTime(fixed);
      const shoot = async (name, full = true) => {
        const file = path.join(dir, `${name}-${theme}-${width}.png`);
        await page.screenshot({ path: file, fullPage: full });
        shots.push(file);
      };
      for (const [name, url] of screens) {
        await page.goto(url);
        await page.waitForLoadState("networkidle");
        await settle(page, 700);
        await shoot(name);
      }
      // The review session, both kinds, without grading anything (so every theme and
      // width sees the same queue): the queue filtered to one kind, and the AI's check
      // answered here (the demo has no AI provider).
      for (const kind of ["flashcard", "short_answer"]) {
        await page.route("**/api/practice/queue*", async (route) => {
          const body = await (await route.fetch()).json();
          body.items = body.items.filter((item) => item.kind === kind);
          await route.fulfill({ json: body });
        });
        await page.route("**/api/practice/items/*/mark", (route) =>
          route.fulfill({ json: QA_MARKING }),
        );
        await page.goto("/practice/review");
        await page.getByRole("heading", { level: 2 }).first().waitFor();
        await settle(page, 400);
        await shoot(`review-${kind}`);
        if (kind === "flashcard") {
          await page.getByRole("button", { name: "Show answer" }).click();
        } else {
          await page
            .getByRole("textbox", { name: "Your answer" })
            .fill(
              "Past ssthresh the window grows by one segment a round trip.",
            );
          await page.getByRole("button", { name: "Check with AI" }).click();
          await page.getByRole("region", { name: "The AI's check" }).waitFor();
        }
        await settle(page, 400);
        await shoot(`review-${kind}-answered`);
        await page.unrouteAll({ behavior: "ignoreErrors" });
      }
      // The plan: earlier days (folded in the agenda) and the block popover, a sheet on
      // phones, for the block in progress and the done one.
      await page.goto("/plan");
      await page.locator('[data-status="now"]').first().waitFor();
      const earlier = page.getByText("Earlier this week");
      if (await earlier.count()) {
        await earlier.click();
        await settle(page, 300);
        await shoot("plan-earlier");
      }
      for (const status of ["now", "done"]) {
        await page.locator(`[data-status="${status}"]`).first().click();
        await page.locator('[role="dialog"][data-state="open"]').waitFor();
        await settle(page, 400);
        await shoot(`plan-popover-${status}`, false);
        await page.keyboard.press("Escape");
        await settle(page, 400);
      }
      // Settings → Reminders and Calendar: a calendar link just made (shown once), then the
      // reminder states a real permission prompt can't reach headless (decision 0024).
      await page.goto("/settings");
      const calendar = page.getByRole("region", {
        name: "Calendar",
        exact: true,
      });
      await calendar
        .getByRole("button", { name: "Create a private calendar link" })
        .click();
      await calendar.getByLabel("Private calendar link").waitFor();
      await calendar.scrollIntoViewIfNeeded();
      await settle(page, 300);
      await shoot("settings-calendar-link", false);
      await page.request.delete("/api/calendar/feed");
      for (const [state, script] of Object.entries(REMINDER_STATES)) {
        const extra = await ctx.newPage();
        await extra.clock.setFixedTime(fixed);
        await extra.addInitScript(script);
        await extra.goto("/settings");
        const reminders = extra.getByRole("region", {
          name: "Reminders",
          exact: true,
        });
        await reminders
          .getByText(
            state === "on" ? "This device" : "Notifications are blocked",
            {
              exact: state === "on",
            },
          )
          .first()
          .waitFor();
        await reminders.scrollIntoViewIfNeeded();
        await settle(extra, 300);
        const file = path.join(
          dir,
          `settings-reminders-${state}-${theme}-${width}.png`,
        );
        await extra.screenshot({ path: file });
        shots.push(file);
        await extra.close();
      }
      // The main dialogs.
      await page.goto(`/modules/${moduleId}?tab=topics`);
      await page
        .getByRole("button", { name: /Slow start and ssthresh/ })
        .first()
        .click();
      await page
        .getByRole("dialog")
        .getByText(/Week 6 slides/)
        .first()
        .waitFor();
      await settle(page);
      await shoot("dialog-linked-pages");
      await page.keyboard.press("Escape");
      await page.goto(`/modules/${moduleId}?tab=materials`);
      await page.getByRole("button", { name: "View Week 6 slides" }).click();
      await page
        .getByRole("dialog", { name: "Week 6 slides" })
        .locator("canvas")
        .first()
        .waitFor();
      await settle(page, 1500);
      await shoot("dialog-viewer");
      await page.keyboard.press("Escape");
      await page.goto("/modules");
      await page.getByRole("button", { name: "New module" }).first().click();
      await page.getByRole("dialog").waitFor();
      await settle(page);
      await shoot("dialog-new-module");
      await ctx.close();
    }
  }
  // Interactions a page-by-page capture can't show: a hovered topic row, the menus, the
  // navigation over scrolled content, and the search results.
  for (const theme of ["light", "dark"]) {
    const ctx = await context(browser, theme, { width: 1440, height: 900 }, 1);
    const page = await ctx.newPage();
    await page.clock.setFixedTime(fixed);
    const shoot = async (name, full = false) => {
      const file = path.join(dir, `${name}-${theme}-1440.png`);
      await page.screenshot({ path: file, fullPage: full });
      shots.push(file);
    };
    await page.goto(`/modules/${moduleId}?tab=topics`);
    await page.getByText("Flow control").first().hover();
    await settle(page, 400);
    await shoot("topic-row-hover");
    await page.mouse.wheel(0, 500);
    await settle(page, 400);
    await shoot("nav-over-tree");
    await page.goto(`/modules/${moduleId}`);
    await page.getByRole("button", { name: "Module actions" }).click();
    await settle(page, 400);
    await shoot("module-menu");
    await page.keyboard.press("Escape");
    await page.goto(`/modules/${moduleId}?tab=materials`);
    await page
      .getByRole("searchbox", { name: "Search materials" })
      .fill("inference congestion window");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await page.getByRole("list", { name: /Results for/ }).waitFor();
    await settle(page, 400);
    await shoot("search-results", true);
    await page.mouse.wheel(0, 400);
    await settle(page, 400);
    await shoot("nav-over-results");
    await ctx.close();

    // A phone with touch: the topic row's "…" menu (pointer: coarse) and the bottom tab bar.
    const phone = await browser.newContext({
      baseURL: `http://localhost:${WEB_PORT}`,
      viewport: { width: 375, height: 812 },
      deviceScaleFactor: 1,
      isMobile: true,
      hasTouch: true,
      locale: "en-GB",
      timezoneId: TIMEZONE,
      colorScheme: theme,
    });
    await phone.addInitScript(
      (value) => localStorage.setItem("studysensei.appearance", value),
      theme,
    );
    const mobile = await phone.newPage();
    await mobile.clock.setFixedTime(fixed);
    await mobile.goto(`/modules/${moduleId}?tab=topics`);
    await mobile
      .getByRole("button", { name: "Actions for Flow control" })
      .click();
    await settle(mobile, 400);
    const file = path.join(dir, `topic-touch-menu-${theme}-375.png`);
    await mobile.screenshot({ path: file });
    shots.push(file);
    await phone.close();
  }
  console.log(`QA: ${shots.length} screenshots in ${dir}`);
}

let failed = false;
try {
  await main();
} catch (error) {
  failed = true;
  console.error(error);
} finally {
  stopAll();
}
if (!failed) console.log("Screenshots done.");
process.exit(failed ? 1 : 0);
