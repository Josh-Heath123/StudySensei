// Check that every relative link and image path in README.md and docs/ (Markdown links,
// <img src>, <source srcset>) points at a file or folder that exists. External links
// (http, https, mailto) and same-page anchors are skipped. `node scripts/check-links.mjs`
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

function markdownFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return markdownFiles(full);
    return name.endsWith(".md") ? [full] : [];
  });
}

const files = [path.join(root, "README.md"), ...markdownFiles(path.join(root, "docs"))];
const patterns = [
  /\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, // [text](target) and ![alt](target "title")
  /<img[^>]*\ssrc="([^"]+)"/g,
  /<source[^>]*\ssrcset="([^"]+)"/g,
  /<a[^>]*\shref="([^"]+)"/g,
];

let checked = 0;
const broken = [];
for (const file of files) {
  // Code blocks hold examples, not links.
  const text = readFileSync(file, "utf8").replace(/```[\s\S]*?```/g, "");
  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) {
      const target = match[1];
      if (/^(https?:|mailto:|#)/.test(target)) continue;
      const clean = decodeURIComponent(target.split("#")[0]);
      if (!clean) continue;
      checked += 1;
      if (!existsSync(path.resolve(path.dirname(file), clean))) {
        broken.push(`${path.relative(root, file)}: ${target}`);
      }
    }
  }
}
console.log(`${files.length} files, ${checked} relative links and images checked`);
if (broken.length) {
  console.log(`Broken:\n  ${broken.join("\n  ")}`);
  process.exit(1);
}
console.log("All resolve.");
