// Run a command while holding a lock file, so two runs never overlap.
//
//   node scripts/with-lock.mjs <lock name> <command…>
//
// `npm run check` uses it: two checks at once (e.g. a background run and the Stop
// hook) would both rebuild the studysensei_test database and fail each other.
// - The lock is `.locks/<name>.lock` at the repo root (gitignored), holding the PID.
// - A second run waits for the first to finish, up to 10 minutes, then runs.
// - A lock whose PID is no longer alive is stale: it's removed and taken over.
import { spawn } from "node:child_process";
import {
  mkdirSync,
  openSync,
  readFileSync,
  statSync,
  unlinkSync,
  writeSync,
  closeSync,
} from "node:fs";
import path from "node:path";

const WAIT_MS = 10 * 60 * 1000;
const POLL_MS = 1000;
// A lock file that's still empty this long after creation lost its writer.
const EMPTY_GRACE_MS = 10 * 1000;

const [name, ...command] = process.argv.slice(2);
if (!name || command.length === 0) {
  console.error("usage: node scripts/with-lock.mjs <lock name> <command…>");
  process.exit(2);
}

const root = path.resolve(import.meta.dirname, "..");
const lockPath = path.join(root, ".locks", `${name}.lock`);

/** True if a process with this PID exists (EPERM: it exists but isn't ours). */
function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

/** Create the lock file with our PID. False if it already exists. */
function tryCreate() {
  try {
    const fd = openSync(lockPath, "wx"); // atomic: fails if the file exists
    writeSync(fd, String(process.pid));
    closeSync(fd);
    return true;
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    return false;
  }
}

/** Try once to take the lock, taking over a stale one. Returns true if it's ours now. */
function tryAcquire() {
  if (tryCreate()) return true;
  // Someone holds it. Is that someone still alive?
  let holder;
  try {
    holder = Number.parseInt(readFileSync(lockPath, "utf8").trim(), 10);
  } catch {
    return false; // removed between our open and read: try again next poll
  }
  if (Number.isNaN(holder)) {
    // Being written right now, or abandoned mid-write: only stale after a grace period.
    let age = 0;
    try {
      age = Date.now() - statSync(lockPath).mtimeMs;
    } catch {
      return false;
    }
    if (age < EMPTY_GRACE_MS) return false;
  } else if (isAlive(holder)) {
    return false;
  }
  console.error(
    `[${name}] removing a stale lock (process ${holder || "unknown"} is gone)`,
  );
  try {
    unlinkSync(lockPath);
  } catch {
    // Another waiter removed it first; fine.
  }
  return tryCreate(); // false if another waiter got there first
}

function release() {
  try {
    if (readFileSync(lockPath, "utf8").trim() === String(process.pid))
      unlinkSync(lockPath);
  } catch {
    // Already gone.
  }
}

mkdirSync(path.dirname(lockPath), { recursive: true });
const started = Date.now();
let announced = false;
while (!tryAcquire()) {
  if (Date.now() - started > WAIT_MS) {
    console.error(
      `[${name}] still locked after 10 minutes (${lockPath}); giving up.`,
    );
    process.exit(1);
  }
  if (!announced) {
    let holder = "another process";
    try {
      holder = `process ${readFileSync(lockPath, "utf8").trim()}`;
    } catch {
      // Gone already; the next try will take it.
    }
    console.error(
      `[${name}] waiting for ${holder} to finish (lock: ${lockPath})…`,
    );
    announced = true;
  }
  await new Promise((resolve) => setTimeout(resolve, POLL_MS));
}

process.on("exit", release);
const child = spawn(command.join(" "), {
  cwd: process.cwd(),
  stdio: "inherit",
  shell: true,
});
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    child.kill(signal);
    release();
    process.exit(130);
  });
}
child.on("exit", (code, signal) => {
  release();
  process.exit(code ?? (signal ? 1 : 0));
});
