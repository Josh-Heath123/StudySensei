// Licence check for every Python package in apps/api's environment (from uv.lock, dev tools
// included) and every npm production dependency (package-lock.json). Run in CI's hygiene job:
// `node scripts/check-licenses.mjs`. The data comes from scripts/license-data.mjs, which also
// feeds THIRD_PARTY_NOTICES.md.
//
// Fails on AGPL, GPL or SSPL, or on a package with no licence information, unless it's in
// scripts/license-allowlist.json with the reason it was reviewed. "MIT OR GPL-3.0" passes
// (one acceptable option is enough); LGPL passes (we only use such libraries, never change
// them). PyMuPDF was rejected for AGPL; this makes that rule enforced.
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  classify,
  npmProductionPackages,
  pythonInstalledPackages,
  pythonKey,
  root,
} from "./license-data.mjs";

const allow = JSON.parse(readFileSync(path.join(root, "scripts/license-allowlist.json"), "utf8"));

let problems = 0;
for (const [ecosystem, packages, key] of [
  ["python", pythonInstalledPackages(), pythonKey],
  ["npm", npmProductionPackages(), (name) => name],
]) {
  const reviewed = Object.fromEntries(
    Object.entries(allow[ecosystem] ?? {}).map(([name, reason]) => [key(name), reason]),
  );
  const counts = { ok: 0, reviewed: 0, forbidden: 0, unknown: 0 };
  for (const pkg of packages) {
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
