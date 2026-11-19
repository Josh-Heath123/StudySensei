import path from "node:path";

import { expect, test } from "@playwright/test";

import { uniqueCode } from "./env";
import { startWorker, stopWorker } from "./worker";

// The first search of a run loads the embedding model in the API process.
const SEARCH_TIMEOUT = 60_000;

test.afterEach(stopWorker);

test("upload a file from the Materials tab; the worker extracts, indexes and searches it", async ({
  page,
  request,
}, testInfo) => {
  const module = await (
    await request.post("/api/modules", {
      data: { code: uniqueCode("MAT101", testInfo), name: "Materials e2e" },
    })
  ).json();

  await page.goto(`/modules/${module.id}?tab=materials`);
  await expect(page.getByText(/No materials yet/)).toBeVisible();

  await page.getByLabel("Files to upload").setInputFiles({
    name: "Week 3 notes.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Week 3\n\n- layered style\n- pipes and filters\n"),
  });
  const staged = page.getByRole("listitem", { name: "Week 3 notes.md" });
  await expect(staged.getByLabel("Kind")).toHaveValue("notes");
  await staged.getByLabel("Title").fill("Week 3 notes");
  await page.getByRole("button", { name: "Upload 1 file" }).click();

  const row = page.getByRole("listitem", { name: "Week 3 notes" });
  await expect(row.getByRole("status")).toHaveText("Waiting to be processed…");

  // The browser sent the real filename (the API checks the type from it).
  const [material] = await (await request.get(`/api/modules/${module.id}/materials`)).json();
  expect(material).toMatchObject({
    original_filename: "Week 3 notes.md",
    content_type: "text/markdown",
    kind: "notes",
    allow_ai: true,
  });

  startWorker();
  // Extraction, then local embedding (the model loads, or downloads on a first run).
  test.setTimeout(180_000);
  await expect(row.getByRole("status")).toHaveText("Ready", { timeout: 150_000 });
  await expect(row).toContainText("1 page");

  // The extracted text, as the chunker will read it.
  await row.getByRole("button", { name: "View Week 3 notes" }).click();
  const viewer = page.getByRole("dialog", { name: "Week 3 notes" });
  await expect(viewer.getByRole("region", { name: "Page 1 text" })).toContainText(
    "- pipes and filters",
  );
  await page.keyboard.press("Escape");

  // Search finds the page, and a result opens it.
  await page.getByRole("searchbox", { name: "Search materials" }).fill("pipes and filters");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const results = page.getByRole("list", { name: "Results for “pipes and filters”" });
  const hit = results.getByRole("button").first();
  // The API loads the embedding model on its first search of the run (seconds on a cold
  // machine), so wait for the answer itself rather than the default 5 s.
  await expect(hit).toBeVisible({ timeout: SEARCH_TIMEOUT });
  await expect(hit).toContainText("Week 3 notes · page 1");
  await expect(hit.locator("mark").first()).toHaveText(/pipes/i);
  await hit.click();
  await expect(
    page.getByRole("dialog", { name: "Week 3 notes" }).getByRole("region", { name: "Page 1 text" }),
  ).toContainText("- layered style");
  await page.keyboard.press("Escape");

  // The same file again is refused, and says why.
  await page.getByLabel("Files to upload").setInputFiles({
    name: "copy.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Week 3\n\n- layered style\n- pipes and filters\n"),
  });
  await page.getByRole("button", { name: "Upload 1 file" }).click();
  await expect(page.getByRole("listitem", { name: "copy.md" }).getByRole("alert")).toHaveText(
    "Not uploaded: This file is already in the module as “Week 3 notes”.",
  );
});

/** True when the canvas has drawn something: a non-zero size and some non-white pixels. */
async function canvasHasInk(canvas: import("@playwright/test").Locator) {
  return canvas.evaluate((element) => {
    // The e2e project has no DOM types: just what this check uses of a canvas.
    type Canvas = {
      width: number;
      height: number;
      getContext(kind: "2d"): {
        getImageData(x: number, y: number, w: number, h: number): { data: ArrayLike<number> };
      };
    };
    const c = element as unknown as Canvas;
    if (c.width === 0 || c.height === 0) return false;
    const pixels = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i]! < 200 || pixels[i + 1]! < 200 || pixels[i + 2]! < 200) return true;
    }
    return false;
  });
}

test("a PDF opens from a search result at its page, drawn by pdf.js", async ({
  page,
  request,
}, testInfo) => {
  const module = await (
    await request.post("/api/modules", {
      data: { code: uniqueCode("MAT102", testInfo), name: "Viewer e2e" },
    })
  ).json();
  await page.goto(`/modules/${module.id}?tab=materials`);

  // The synthetic 3-page lecture: page 1 layers, page 2 a figure, page 3 pipes and filters.
  await page
    .getByLabel("Files to upload")
    .setInputFiles(path.resolve(import.meta.dirname, "../../api/tests/fixtures/lecture.pdf"));
  await page.getByRole("button", { name: "Upload 1 file" }).click();
  const row = page.getByRole("listitem", { name: "lecture" });
  startWorker();
  test.setTimeout(180_000);
  await expect(row.getByRole("status")).toHaveText(/^Ready/, { timeout: 150_000 });

  await page.getByRole("searchbox", { name: "Search materials" }).fill("pipes and filters");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const hit = page
    .getByRole("list", { name: "Results for “pipes and filters”" })
    .getByRole("button")
    .first();
  await expect(hit).toBeVisible({ timeout: SEARCH_TIMEOUT });
  await expect(hit).toContainText("lecture · page 3");
  await hit.click();

  const viewer = page.getByRole("dialog", { name: "lecture" });
  await expect(viewer.getByText("Page 3 of 3")).toBeVisible();
  await expect(viewer.getByRole("button", { name: /^Page 3/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
  const page3 = viewer.getByRole("region", { name: "Page 3", exact: true });
  await expect(page3).toHaveAttribute("aria-busy", "false", { timeout: 20_000 });
  const canvas = viewer.getByRole("img", { name: "Page 3 of lecture" });
  expect(await canvasHasInk(canvas)).toBe(true);

  // Jump to page 1 with the page box.
  await viewer.getByLabel("Go to page").fill("1");
  await viewer.getByLabel("Go to page").press("Enter");
  await expect(viewer.getByText("Page 1 of 3")).toBeVisible();
  const page1 = viewer.getByRole("region", { name: "Page 1", exact: true });
  await expect(page1).toHaveAttribute("aria-busy", "false", { timeout: 20_000 });
  const first = viewer.getByRole("img", { name: "Page 1 of lecture" });
  const size = await first.boundingBox();
  expect(size!.width).toBeGreaterThan(100);
  expect(await canvasHasInk(first)).toBe(true);
  await expect(viewer.getByText(/Couldn't show the PDF/)).toHaveCount(0);
});
