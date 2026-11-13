import path from "node:path";

/** Shared by playwright.config.ts and specs that start the worker themselves. */
export const E2E_DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  "postgresql+asyncpg://studysensei:studysensei@localhost:5433/studysensei_e2e";

/** Uploaded files from e2e runs: gitignored (data/), and away from dev uploads. */
export const E2E_STORAGE_DIR = path.resolve(import.meta.dirname, "../../../data/e2e-materials");
