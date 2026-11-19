import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import path from "node:path";

import { E2E_DATABASE_URL, E2E_STORAGE_DIR } from "./env";

let worker: ChildProcess | undefined;

/** The real job worker, on the e2e database and storage. Stop it with `stopWorker`. */
export function startWorker() {
  worker = spawn("uv", ["run", "--directory", "../api", "python", "-m", "app.jobs.worker"], {
    cwd: path.resolve(import.meta.dirname, ".."),
    env: {
      ...process.env,
      DATABASE_URL: E2E_DATABASE_URL,
      STORAGE_DIR: E2E_STORAGE_DIR,
      WORKER_POLL_SECONDS: "0.2",
    },
    stdio: "ignore",
    // Its own process group, so the whole tree can be stopped (POSIX).
    detached: process.platform !== "win32",
  });
}

export function stopWorker() {
  // uv starts python as a child: stop the whole tree (on Windows, kill() only stops uv).
  if (worker?.pid !== undefined) {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(worker.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-worker.pid, "SIGTERM");
    }
  }
  worker = undefined;
}
