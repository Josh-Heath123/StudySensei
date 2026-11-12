// `npm run dev`: start Postgres, migrate, seed, then run the API and web app together.
// Plain Node so it behaves the same in PowerShell, cmd and Git Bash.
import { execSync, spawn } from "node:child_process";

const run = (cmd) => execSync(cmd, { stdio: "inherit" });

console.log("Starting Postgres (docker compose)…");
try {
  run("docker compose up -d --wait db");
} catch {
  console.error("\nCould not start Postgres. Is Docker Desktop running?\n");
  process.exit(1);
}

console.log("Applying migrations and seeding the local user…");
run("uv run --directory apps/api alembic upgrade head");
run("uv run --directory apps/api python -m app.seed");

const child = spawn(
  "npx",
  [
    "concurrently",
    "--kill-others-on-fail",
    "--names",
    "api,web",
    "--prefix-colors",
    "blue,magenta",
    '"uv run --directory apps/api uvicorn app.main:app --reload --port 8000"',
    '"npm run dev -w apps/web"',
  ],
  { stdio: "inherit", shell: true },
);
child.on("exit", (code) => process.exit(code ?? 0));
