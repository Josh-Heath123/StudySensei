import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { E2E_DATABASE_URL, E2E_STORAGE_DIR } from "./env";

let worker: ChildProcess | undefined;

test.afterEach(() => {
  // uv starts python as a child: stop the whole tree (on Windows, kill() only stops uv).
  if (worker?.pid !== undefined) {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(worker.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-worker.pid, "SIGTERM");
    }
  }
  worker = undefined;
});

/** The real job worker, on the e2e database and storage. */
function startWorker() {
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

test("upload a file from the Materials tab; the worker makes it ready", async ({
  page,
  request,
}) => {
  const module = await (
    await request.post("/api/modules", { data: { code: "MAT101", name: "Materials e2e" } })
  ).json();

  await page.goto(`/modules/${module.id}?tab=materials`);
  await expect(page.getByText(/No materials yet/)).toBeVisible();

  await page.getByLabel("Files to upload").setInputFiles({
    name: "Week 3 notes.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Week 3\n\n- layered style\n- pipes and filters\n"),
  });
  const staged = page.getByRole("listitem", { name: "Week 3 notes.md" });
  await expect(staged.getByLabel("Kind")).toHaveValue("notes");
  await staged.getByLabel("Title").fill("Week 3 notes");
  await page.getByRole("button", { name: "Upload 1 file" }).click();

  const row = page.getByRole("listitem", { name: "Week 3 notes" });
  await expect(row.getByRole("status")).toHaveText("Waiting to be processed…");

  // The browser sent the real filename (the API checks the type from it).
  const [material] = await (await request.get(`/api/modules/${module.id}/materials`)).json();
  expect(material).toMatchObject({
    original_filename: "Week 3 notes.md",
    content_type: "text/markdown",
    kind: "notes",
    allow_ai: true,
  });

  startWorker();
  await expect(row.getByRole("status")).toHaveText("Ready", { timeout: 30_000 });

  // The same file again is refused, and says why.
  await page.getByLabel("Files to upload").setInputFiles({
    name: "copy.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Week 3\n\n- layered style\n- pipes and filters\n"),
  });
  await page.getByRole("button", { name: "Upload 1 file" }).click();
  await expect(page.getByRole("listitem", { name: "copy.md" }).getByRole("alert")).toHaveText(
    "Not uploaded: This file is already in the module as “Week 3 notes”.",
  );
});
