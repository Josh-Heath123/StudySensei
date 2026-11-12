// Claude Code Stop hook: don't let a session finish with failing checks.
//
// - No changes in `git status --porcelain` → exit 0 immediately (nothing to check).
// - Changes → run `npm run check`. Pass → exit 0. Fail → exit 2 with the tail of the
//   output on stderr, which blocks the stop and hands the failure back to Claude.
// - If Claude is already continuing because of this hook (stop_hook_active) and the
//   checks still fail, let it stop with a warning instead of looping forever.
import { execSync, spawnSync } from "node:child_process";

const root = process.env.CLAUDE_PROJECT_DIR ?? process.cwd();

let input = {};
try {
  const raw = await new Promise((resolve) => {
    let data = "";
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
  });
  input = raw ? JSON.parse(raw) : {};
} catch {
  // Malformed input: fall through and behave as a first stop.
}

const changes = execSync("git status --porcelain", { cwd: root, encoding: "utf8" }).trim();
if (!changes) process.exit(0);

const result = spawnSync("npm run check", {
  cwd: root,
  shell: true,
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
if (result.status === 0) process.exit(0);

const tail = `${result.stdout ?? ""}${result.stderr ?? ""}`.split("\n").slice(-60).join("\n");

if (input.stop_hook_active) {
  console.log(
    JSON.stringify({
      systemMessage: "npm run check is still failing after a retry; stopping anyway. Fix before committing.",
    }),
  );
  process.exit(0);
}

console.error(`npm run check failed. Fix it before finishing (or say why it can't be fixed).\n\n${tail}`);
process.exit(2);
