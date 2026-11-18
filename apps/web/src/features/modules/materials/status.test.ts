import type { Material } from "./api";
import { pageDetails, statusText, topicStateText } from "./status";

const material = (overrides: Partial<Material>): Material => ({
  id: "m",
  module_id: "m1",
  kind: "slides",
  title: "Week 3",
  original_filename: "w3.pdf",
  content_type: "application/pdf",
  size_bytes: 10,
  sha256: "a".repeat(64),
  page_count: null,
  scanned_page_count: null,
  status: "uploaded",
  error: null,
  retrying: false,
  allow_ai: true,
  created_at: "",
  updated_at: "",
  ...overrides,
});

test("says how far processing has got", () => {
  expect(statusText(material({})).text).toBe("Waiting to be processed…");
  expect(statusText(material({ status: "processing" })).text).toBe("Extracting text…");
  expect(statusText(material({ status: "processing", page_count: 4 })).text).toBe(
    "Indexing for search…",
  );
  expect(
    statusText(material({ status: "processing", error: "Server hiccup.", retrying: true })),
  ).toEqual({ text: "Retrying: Server hiccup.", tone: "muted" });
  expect(
    statusText(material({ status: "failed", error: "The PDF is password-protected." })),
  ).toEqual({ text: "Failed: The PDF is password-protected.", tone: "danger" });
});

test("ready says just that; the scanned count is on the details line, once", () => {
  const ready = { status: "ready" as const, page_count: 12 };
  expect(statusText(material({ ...ready, scanned_page_count: 0 }))).toEqual({
    text: "Ready",
    tone: "ink",
  });
  expect(statusText(material({ ...ready, scanned_page_count: 4 }))).toEqual({
    text: "Ready",
    tone: "ink",
  });
  expect(pageDetails(material({ ...ready, scanned_page_count: 4 }))).toEqual([
    "12 pages",
    "4 scanned",
  ]);
});

test("page details appear once pages are known", () => {
  expect(pageDetails(material({}))).toEqual([]);
  expect(pageDetails(material({ page_count: 1, scanned_page_count: 0 }))).toEqual(["1 page"]);
  expect(pageDetails(material({ page_count: 12, scanned_page_count: 4 }))).toEqual([
    "12 pages",
    "4 scanned",
  ]);
});

test("topic lines say what was found, why it failed, or that it's waiting", () => {
  expect(topicStateText({ state: "analysed", error: null, topics: 7 })).toEqual({
    text: "Topics: 7 found",
    tone: "default",
  });
  expect(topicStateText({ state: "failed", error: "Bad shape.", topics: 0 })).toEqual({
    text: "Topics couldn't be found: Bad shape.",
    tone: "danger",
  });
  expect(topicStateText({ state: "failed", error: null, topics: 0 }).text).toBe(
    "Topics couldn't be found.",
  );
  expect(topicStateText({ state: "waiting", error: null, topics: 0 }).tone).toBe("muted");
});
