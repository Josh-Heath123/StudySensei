// `npm run e2e`: rebuild the studysensei_e2e database, then run Playwright against
// its own API (:8001) and web app (:5174). Never touches the dev database or ports.
// In CI the database comes from a service container, so Docker is skipped.
import { execSync } from "node:child_process";

const DB = "studysensei_e2e";
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  `postgresql+asyncpg://studysensei:studysensei@localhost:5433/${DB}`;
const run = (cmd, env = {}) =>
  execSync(cmd, { stdio: "inherit", env: { ...process.env, ...env } });

if (!process.env.CI) {
  console.log("Starting Postgres (docker compose)…");
  try {
    run("docker compose up -d --wait db");
  } catch {
    console.error("\nCould not start Postgres. Is Docker Desktop running?\n");
    process.exit(1);
  }
  const exists = execSync(
    `docker compose exec -T db psql -U studysensei -d studysensei -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB}'"`,
  )
    .toString()
    .trim();
  if (exists !== "1") {
    console.log(`Creating database ${DB}…`);
    run(`docker compose exec -T db psql -U studysensei -d studysensei -c "CREATE DATABASE ${DB}"`);
  }
}

console.log(`Rebuilding ${DB} and seeding the local user…`);
const api = { DATABASE_URL };
run("uv run --directory apps/api alembic downgrade base", api);
run("uv run --directory apps/api alembic upgrade head", api);
run("uv run --directory apps/api python -m app.seed", api);

const args = process.argv.slice(2).join(" ");
try {
  run(`npx playwright test -c apps/web/playwright.config.ts ${args}`.trim(), {
    E2E_DATABASE_URL: DATABASE_URL,
  });
} catch {
  process.exit(1);
}
