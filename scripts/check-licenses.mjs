// Licence check for every Python package in apps/api's environment (from uv.lock) and every
// npm production dependency. Run in CI's hygiene job: `node scripts/check-licenses.mjs`.
//
// Fails on AGPL, GPL or SSPL, or on a package with no licence information, unless it's in
// scripts/license-allowlist.json with the reason it was reviewed. "MIT OR GPL-3.0" passes
// (one acceptable option is enough); LGPL passes (we only use such libraries, never
// change them). PyMuPDF was rejected for AGPL (ADR 0001 era); this makes that rule enforced.
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const allow = JSON.parse(readFileSync(path.join(root, "scripts/license-allowlist.json"), "utf8"));

// GPL in any version or variant except the Lesser one, Affero, and SSPL.
const FORBIDDEN = [
  /\bAGPL/i,
  /\bAffero\b/i,
  /(?<![L])GPL/i,
  /GNU General Public/i,
  /\bSSPL\b/i,
  /Server Side Public/i,
];

/** "ok", "forbidden" or "unknown" for one licence string (an SPDX expression or a name). */
export function classify(license) {
  const text = (license ?? "").trim();
  if (!text || /^(unknown|unlicensed|see license in .*|none)$/i.test(text)) return "unknown";
  const options = text.replace(/[()]/g, " ").split(/\s+OR\s+/i);
  const okOption = (option) =>
    option.split(/\s+AND\s+/i).every((part) => !FORBIDDEN.some((re) => re.test(part)));
  return options.some(okOption) ? "ok" : "forbidden";
}

function npmPackages() {
  const found = JSON.parse(execSync("npm query .prod", { cwd: root, encoding: "utf8" }));
  return found
    .filter((pkg) => pkg.name && pkg.version && !pkg.location?.startsWith("apps/"))
    .map((pkg) => {
      let license = pkg.license;
      if (license && typeof license === "object") license = license.type;
      if (!license && Array.isArray(pkg.licenses)) {
        license = pkg.licenses.map((item) => item.type ?? item).join(" OR ");
      }
      return { name: pkg.name, version: pkg.version, license: license ?? "" };
    });
}

function pythonPackages() {
  // apps/api's environment (uv sync --locked), read by a small script that prints JSON.
  const output = execSync("uv run --directory apps/api python -I ../../scripts/python-licenses.py", {
    cwd: root,
    encoding: "utf8",
  });
  return JSON.parse(output);
}

let problems = 0;
for (const [ecosystem, packages] of [
  ["python", pythonPackages()],
  ["npm", npmPackages()],
]) {
  // Python names compare the PEP 503 way: py_rust_stemmers is py-rust-stemmers.
  const key = (name) => (ecosystem === "python" ? name.toLowerCase().replace(/[-_.]+/g, "-") : name);
  const reviewed = Object.fromEntries(
    Object.entries(allow[ecosystem] ?? {}).map(([name, reason]) => [key(name), reason]),
  );
  const counts = { ok: 0, reviewed: 0, forbidden: 0, unknown: 0 };
  for (const pkg of packages.sort((a, b) => a.name.localeCompare(b.name))) {
    const verdict = classify(pkg.license);
    if (verdict === "ok") {
      counts.ok += 1;
    } else if (reviewed[key(pkg.name)]) {
      counts.reviewed += 1;
    } else {
      counts[verdict] += 1;
      problems += 1;
      console.log(`${ecosystem}: ${pkg.name} ${pkg.version}: ${verdict} licence "${pkg.license}"`);
    }
  }
  console.log(
    `${ecosystem}: ${packages.length} packages, ${counts.ok} ok, ${counts.reviewed} allow-listed, ` +
      `${counts.forbidden} forbidden, ${counts.unknown} unknown`,
  );
}
if (problems) {
  console.log(
    `\n${problems} package(s) need review. A real AGPL/GPL/SSPL dependency must be replaced; a ` +
      "package whose licence is fine but unreadable goes in scripts/license-allowlist.json with the reason.",
  );
  process.exit(1);
}
