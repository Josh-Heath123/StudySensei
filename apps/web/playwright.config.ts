import { defineConfig, devices } from "@playwright/test";

import { E2E_DATABASE_URL, E2E_STORAGE_DIR } from "./e2e/env";

/**
 * End-to-end tests against the real stack, on their own ports and database so
 * they never touch `npm run dev` (:8000 / :5173, db `studysensei`). Run them with
 * `npm run e2e` from the repo root, which prepares the `studysensei_e2e` database.
 */
const API_PORT = 8001;
const WEB_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // one local user, and only one open session at a time
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run --directory ../api uvicorn app.main:app --port ${API_PORT}`,
      url: `http://localhost:${API_PORT}/health`,
      env: { DATABASE_URL: E2E_DATABASE_URL, STORAGE_DIR: E2E_STORAGE_DIR },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { API_PROXY_TARGET: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
