// `npm run check:steps`: every check CI runs (except e2e), in parallel, with timings.
//
//   node scripts/check.mjs [--serial]
//
// - Two phases. First the static steps (ruff, ruff format, prettier, eslint, mypy, tsc) in
//   parallel, with Postgres starting (`docker compose up -d --wait db`). Then pytest and
//   vitest in parallel: pytest on 4 pytest-xdist workers (each with its own
//   studysensei_gwN_test database), vitest on 8 threads. Running all of it at once was
//   slower: the test runners starved each other of CPU.
// - The tests run even if a static step failed, so one run reports every failure.
// - Each step's output goes to .locks/check/<step>.log. A line is printed as each step
//   ends, and a failed or timed-out step's last lines are printed at the end under its
//   name, so it's obvious which one failed.
// - Every step has a time limit. A step past it is killed (with its child processes) and
//   reported as timed out, so a hung step (vitest once hung for 48 minutes) can't hold
//   the check lock forever.
// - `--serial` runs the steps one at a time (to measure each on its own).
// `npm run check` wraps this in scripts/with-lock.mjs so two checks never overlap.
import { spawn, spawnSync } from "node:child_process";
import { createWriteStream, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const logDir = path.join(root, ".locks", "check");
const MINUTE = 60 * 1000;
const TAIL_LINES = 60;

const api = "uv run --directory apps/api";
const phases = [
  [
    { name: "ruff", cmd: `${api} ruff check .`, limit: 3 * MINUTE },
    { name: "ruff format", cmd: `${api} ruff format --check .`, limit: 3 * MINUTE },
    { name: "prettier", cmd: "npm run format:check -w apps/web", limit: 3 * MINUTE },
    { name: "eslint", cmd: "npm run lint -w apps/web", limit: 3 * MINUTE },
    { name: "mypy", cmd: `${api} mypy`, limit: 5 * MINUTE },
    { name: "tsc", cmd: "npm run typecheck -w apps/web", limit: 3 * MINUTE },
    { name: "postgres", cmd: "docker compose up -d --wait db", limit: 3 * MINUTE },
  ],
  [
    { name: "pytest", cmd: `${api} pytest -n 4 -p no:cacheprovider`, limit: 8 * MINUTE },
    // About 20 s normally. Vitest has twice hung on Windows before finishing any file (once for
    // 48 minutes); a run that times out is retried once. A failing test is never retried.
    {
      name: "vitest",
      cmd: "npm run test -w apps/web -- --maxWorkers=8",
      limit: 2 * MINUTE,
      retryOnTimeout: true,
    },
  ],
];
const steps = phases.flat();

const serial = process.argv.includes("--serial");
const width = Math.max(...steps.map((step) => step.name.length));
const seconds = (ms) => `${(ms / 1000).toFixed(1)} s`;

/** Kill a step and everything it started (npm → node → workers). */
function killTree(child) {
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    try {
      process.kill(-child.pid, "SIGKILL"); // the step's process group
    } catch {
      // Already gone.
    }
  }
}

async function run(step) {
  const result = await runOnce(step);
  if (result.timedOut && step.retryOnTimeout) {
    console.log(`[check] ${step.name} timed out after ${seconds(step.limit)}; retrying once`);
    const retry = await runOnce(step);
    return { ...retry, ms: result.ms + retry.ms, retried: true };
  }
  return result;
}

function runOnce(step) {
  const logPath = path.join(logDir, `${step.name.replace(/\s+/g, "-")}.log`);
  const log = createWriteStream(logPath);
  const started = Date.now();
  return new Promise((resolve) => {
    const child = spawn(step.cmd, {
      cwd: root,
      shell: true,
      detached: process.platform !== "win32", // its own group, so the whole tree can be killed
      env: { ...process.env, FORCE_COLOR: "0" },
    });
    child.stdout.pipe(log, { end: false });
    child.stderr.pipe(log, { end: false });
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      killTree(child);
    }, step.limit);
    child.on("close", (code) => {
      clearTimeout(timer);
      log.end(() => {
        const result = { ...step, logPath, ms: Date.now() - started, code, timedOut };
        result.ok = code === 0 && !timedOut;
        const status = result.ok ? "ok  " : timedOut ? "TIME" : "FAIL";
        const note = timedOut ? ` (killed after ${seconds(step.limit)})` : result.ok ? "" : ` (exit ${code})`;
        console.log(`[check] ${status} ${step.name.padEnd(width)} ${seconds(result.ms).padStart(8)}${note}`);
        resolve(result);
      });
    });
  });
}

mkdirSync(logDir, { recursive: true });
const started = Date.now();
console.log(
  `[check] ${steps.length} steps${serial ? ", one at a time" : " in two parallel phases"}; logs in .locks/check/`,
);
const results = [];
for (const phase of phases) {
  if (serial) {
    for (const step of phase) results.push(await run(step));
  } else {
    results.push(...(await Promise.all(phase.map(run))));
  }
}

const failed = results.filter((result) => !result.ok);
for (const result of failed) {
  const lines = readFileSync(result.logPath, "utf8").trimEnd().split(/\r?\n/);
  console.log(`\n──── ${result.name} ${result.timedOut ? "TIMED OUT" : "FAILED"}: last ${Math.min(TAIL_LINES, lines.length)} lines of ${path.relative(root, result.logPath)} ────`);
  console.log(lines.slice(-TAIL_LINES).join("\n"));
}

console.log("\n[check] step times:");
for (const result of results) {
  const status = result.ok ? "ok" : result.timedOut ? "timed out" : "FAILED";
  const retried = result.retried ? " (after a timed-out first run)" : "";
  console.log(`  ${result.name.padEnd(width)} ${seconds(result.ms).padStart(8)}  ${status}${retried}`);
}
console.log(`  ${"total".padEnd(width)} ${seconds(Date.now() - started).padStart(8)}  (wall)`);
if (failed.length) {
  console.log(`\n[check] FAILED: ${failed.map((result) => result.name).join(", ")}`);
  process.exit(1);
}
console.log("\n[check] all steps passed");
