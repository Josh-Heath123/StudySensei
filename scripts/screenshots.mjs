// `npm run screenshots`: the README's screenshots of the real app, with synthetic demo data.
//
// Like scripts/e2e.mjs it uses its own database (studysensei_demo, rebuilt each run), ports
// (API :8002, web :5176) and storage folder (data/demo-materials), so it never touches the dev
// stack. It seeds the demo (apps/api/scripts/demo_seed.py: original text, the real extraction
// and indexing pipeline, no AI keys), takes the shots with Playwright at 1440×900 and device
// scale 2 with the date fixed, frames each in a 2 px ink border, and stops everything it started.
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
// The demo's "now": a Monday morning. Sessions, deadlines and tasks are seeded around it.
const NOW = "2026-11-16T10:40:00+02:00";
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
};
const run = (cmd, extra = {}) =>
  execSync(cmd, { cwd: root, stdio: "inherit", env: { ...env, ...extra } });
const children = [];

function stopAll() {
  for (const child of children.splice(0)) {
    if (child.pid === undefined) continue;
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
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
    if (code && children.includes(child)) console.error(`${name} exited (${code}):\n${output}`);
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

/** Re-render a screenshot inside a 2 px ink frame, at the same pixel density. */
async function frame(browser, png, file) {
  // A PNG's width and height are big-endian at bytes 16 and 20; CSS pixels are half (scale 2).
  const width = png.readUInt32BE(16) / 2;
  const height = png.readUInt32BE(20) / 2;
  const page = await browser.newPage({
    viewport: { width: width + 4, height: height + 4 },
    deviceScaleFactor: 2,
  });
  const src = `data:image/png;base64,${png.toString("base64")}`;
  await page.setContent(
    `<body style="margin:0"><div id="f" style="border:2px solid #111;width:${width}px;` +
      `height:${height}px"><img src="${src}" style="display:block;width:100%;height:100%"></div></body>`,
  );
  await page.locator("#f").screenshot({ path: path.join(outDir, file) });
  await page.close();
  const kb = Math.round(statSync(path.join(outDir, file)).size / 1024);
  console.log(`  ${file}: ${kb} KB`);
}

async function context(browser) {
  return browser.newContext({
    baseURL: `http://localhost:${WEB_PORT}`,
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    locale: "en-GB",
    timezoneId: TIMEZONE,
    colorScheme: "light",
  });
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
    run(`docker compose exec -T db psql -U studysensei -d studysensei -c "CREATE DATABASE ${DB}"`);
  }
  rmSync(STORAGE_DIR, { recursive: true, force: true });
  run("uv run --directory apps/api alembic downgrade base");
  run("uv run --directory apps/api alembic upgrade head");
  run("uv run --directory apps/api python -m app.seed");
  run(`uv run --directory apps/api python -m scripts.demo_seed --now ${NOW}`);

  console.log("Starting the API and the web app on their own ports…");
  start("API", `uv run uvicorn app.main:app --port ${API_PORT}`, path.join(root, "apps", "api"));
  start("web", `npx vite --port ${WEB_PORT} --strictPort`, path.join(root, "apps", "web"), {
    API_PROXY_TARGET: `http://localhost:${API_PORT}`,
  });
  await waitFor(`http://localhost:${API_PORT}/health`, "The API");
  await waitFor(`http://localhost:${WEB_PORT}`, "The web app");

  const modules = await (await fetch(`http://localhost:${API_PORT}/modules`)).json();
  const module = modules.find((item) => item.code === "NET201");
  if (!module) throw new Error("The demo module NET201 wasn't seeded");

  mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const fixed = new Date(NOW).getTime();
  try {
    // Today, Topics and the viewer: the date is fixed, timers run (pdf.js needs them).
    const ctx = await context(browser);
    const page = await ctx.newPage();
    await page.clock.setFixedTime(fixed);

    await page.goto("/");
    await page.getByText("Semester test 2").first().waitFor();
    await page.getByLabel("Database: Connected").waitFor();
    await page.waitForTimeout(800);
    // The whole page, so the deadlines under the day timeline are in it too.
    await frame(browser, await page.screenshot({ fullPage: true }), "today.png");

    await page.goto(`/modules/${module.id}?tab=topics`);
    await page.getByRole("button", { name: /Slow start and ssthresh/ }).first().click();
    const pages = page.getByRole("dialog");
    await pages.waitFor();
    await pages.getByText(/Week 6 slides/).first().waitFor();
    await page.waitForTimeout(800);
    await frame(browser, await page.screenshot(), "topics.png");
    await page.keyboard.press("Escape");

    await page.goto(`/modules/${module.id}?tab=materials`);
    await page.getByRole("searchbox", { name: "Search materials" }).fill("slow start threshold");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    const results = page.getByRole("list", { name: "Results for “slow start threshold”" });
    const hit = results.getByRole("button").first();
    await hit.waitFor();
    console.log(`  first search result: ${(await hit.innerText()).split("\n")[0]}`);
    await hit.click();
    const viewer = page.getByRole("dialog", { name: "Week 6 slides" });
    await viewer.getByText(/Page \d+ of 6/).waitFor();
    await viewer.locator("canvas").first().waitFor();
    await page.waitForTimeout(2000); // pdf.js draws the page
    await frame(browser, await page.screenshot(), "viewer.png");
    await ctx.close();

    // A running session: a paused clock, so the timer shows exactly 18 minutes in.
    const sessionCtx = await context(browser);
    const sessionPage = await sessionCtx.newPage();
    await sessionPage.clock.install({ time: fixed });
    await sessionPage.clock.pauseAt(fixed + 1000);
    await sessionPage.goto("/");
    await sessionPage.getByRole("button", { name: "Start session" }).click();
    const dialog = sessionPage.getByRole("dialog", { name: "Start a study session" });
    await dialog.getByLabel("Module").selectOption(module.id);
    await dialog.getByLabel("Topic (optional)").selectOption({ label: "Slow start and ssthresh" });
    await dialog.getByRole("button", { name: "Start" }).click();
    await sessionPage.getByRole("timer").waitFor();
    await sessionPage.clock.runFor(18 * 60 * 1000);
    await sessionPage.getByRole("timer").filter({ hasText: "32:00" }).waitFor();
    await frame(browser, await sessionPage.screenshot(), "session.png");
    await sessionCtx.close();
  } finally {
    await browser.close();
  }
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
