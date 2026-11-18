// `npm run assets`: render the README banners and the GitHub social preview from
// docs/assets/src/banner.html with Playwright and the self-hosted Inter (no network, no new
// dependencies). Writes docs/assets/banner-light.png, banner-dark.png, social-preview.png
// and social-preview-dark.png.
import { statSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

const root = path.resolve(import.meta.dirname, "..");
const template = pathToFileURL(
  path.join(root, "docs", "assets", "src", "banner.html"),
).href;
const out = (file) => path.join(root, "docs", "assets", file);

const VARIANTS = [
  {
    file: "banner-light.png",
    theme: "light",
    width: 1600,
    height: 400,
    scale: 2,
  },
  {
    file: "banner-dark.png",
    theme: "dark",
    width: 1600,
    height: 400,
    scale: 2,
  },
  // GitHub's social preview: 1280×640, shown as is (upload one in the repository settings).
  {
    file: "social-preview.png",
    theme: "light",
    width: 1280,
    height: 640,
    scale: 1,
    layout: "social",
  },
  {
    file: "social-preview-dark.png",
    theme: "dark",
    width: 1280,
    height: 640,
    scale: 1,
    layout: "social",
  },
];

const browser = await chromium.launch();
try {
  for (const variant of VARIANTS) {
    const page = await browser.newPage({
      viewport: { width: variant.width, height: variant.height },
      deviceScaleFactor: variant.scale,
    });
    const query = new URLSearchParams({
      theme: variant.theme,
      width: String(variant.width),
      height: String(variant.height),
      layout: variant.layout ?? "banner",
    });
    await page.goto(`${template}?${query}`);
    await page.evaluate(() => document.fonts.ready);
    const fonts = await page.evaluate(() =>
      [...document.fonts]
        .filter((font) => font.status === "loaded")
        .map((font) => font.family),
    );
    if (!fonts.includes("Inter")) {
      throw new Error(
        `Fonts didn't load (got ${fonts.join(", ") || "none"}); run npm install`,
      );
    }
    await page.screenshot({ path: out(variant.file) });
    await page.close();
    const kb = Math.round(statSync(out(variant.file)).size / 1024);
    console.log(
      `${variant.file}: ${variant.width * variant.scale}×${variant.height * variant.scale}, ${kb} KB`,
    );
  }
} finally {
  await browser.close();
}
