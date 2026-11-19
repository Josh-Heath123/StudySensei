import path from "node:path";

import { test as base } from "@playwright/test";

export { expect } from "@playwright/test";
export type { APIRequestContext, Page, Route } from "@playwright/test";

/**
 * Playwright's `test`, with the browser's speech recognition hidden on every page (see
 * fixtures/no-speech.js: headless Chromium crashes on it). voice.spec.ts uses the plain
 * `test` and injects its own fakes instead.
 */
export const test = base.extend({
  page: async ({ page }, provide) => {
    await page.addInitScript({ path: path.resolve(import.meta.dirname, "fixtures/no-speech.js") });
    await provide(page);
  },
});
