// Licence data shared by the CI licence check (scripts/check-licenses.mjs) and the
// THIRD_PARTY_NOTICES.md generator (scripts/third-party-notices.mjs).
//
// - npm: package-lock.json, which records every package's licence for every platform, so the
//   answer is the same on Windows and in CI with no install.
// - Python: each package's own metadata in apps/api's environment (scripts/python-licenses.py).
//   Production packages are those `uv export --no-dev` lists from uv.lock. A package that's only
//   installed on some platforms (a marker such as sys_platform == 'win32') takes its licence
//   from PyPI's metadata for that exact version instead, so every machine writes the same file.
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

export const root = path.resolve(import.meta.dirname, "..");

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

/** PEP 503: py_rust_stemmers and Py-Rust-Stemmers are the same package. */
export const pythonKey = (name) => name.toLowerCase().replace(/[-_.]+/g, "-");

const byName = (a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version);

/** npm production dependencies from package-lock.json: [{name, version, license}]. */
export function npmProductionPackages() {
  const lock = JSON.parse(readFileSync(path.join(root, "package-lock.json"), "utf8"));
  const found = new Map();
  for (const [where, pkg] of Object.entries(lock.packages)) {
    if (!where.includes("node_modules/") || pkg.dev || pkg.link) continue;
    const name = where.split("node_modules/").pop();
    let license = pkg.license;
    if (license && typeof license === "object") license = license.type;
    found.set(`${name}@${pkg.version}`, { name, version: pkg.version, license: license ?? "" });
  }
  return [...found.values()].sort(byName);
}

/** Every package installed in apps/api's environment (dev tools too): [{name, version, license}]. */
export function pythonInstalledPackages() {
  const output = execSync(
    "uv run --directory apps/api python -I ../../scripts/python-licenses.py",
    { cwd: root, encoding: "utf8" },
  );
  return JSON.parse(output).sort(byName);
}

/** The same rule as python-licenses.py, applied to PyPI's JSON for one release. */
function licenseFromPypi(info) {
  let license = info.license_expression || "";
  if (!license && info.license && info.license.length < 200) {
    license = info.license.trim().split(/\r?\n/)[0];
  }
  if (!license || license.toUpperCase() === "UNKNOWN") {
    license = (info.classifiers ?? [])
      .filter((c) => c.startsWith("License ::"))
      .map((c) => c.split("::").pop().trim())
      .filter((c) => c !== "OSI Approved")
      .join(" OR ");
  }
  return license;
}

/** Python production dependencies from uv.lock: [{name, version, license}]. */
export async function pythonProductionPackages() {
  const exported = execSync(
    "uv export --directory apps/api --no-dev --frozen --no-hashes --no-header --no-emit-project",
    { cwd: root, encoding: "utf8" },
  );
  const installed = new Map(pythonInstalledPackages().map((pkg) => [pythonKey(pkg.name), pkg]));
  const packages = [];
  for (const line of exported.split(/\r?\n/)) {
    const match = /^([A-Za-z0-9_.-]+)==([^\s;]+)\s*(;.*)?$/.exec(line.trim());
    if (!match) continue;
    const [, name, version, marker] = match;
    let license;
    if (marker || !installed.has(pythonKey(name))) {
      const response = await fetch(`https://pypi.org/pypi/${name}/${version}/json`);
      if (!response.ok) throw new Error(`PyPI has no ${name} ${version} (${response.status})`);
      license = licenseFromPypi((await response.json()).info);
    } else {
      license = installed.get(pythonKey(name)).license;
    }
    packages.push({ name, version, license });
  }
  return packages.sort(byName);
}
