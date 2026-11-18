import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule } from "../fixtures";
import type { Material, SearchResult, SearchResults } from "./api";

function aMaterial(overrides: Partial<Material> = {}): Material {
  return {
    id: "mat1",
    module_id: "m1",
    kind: "slides",
    title: "CH03 slides",
    original_filename: "CH03.pptx",
    content_type: "application/pdf",
    size_bytes: 1024,
    sha256: "a".repeat(64),
    page_count: 3,
    scanned_page_count: 0,
    status: "ready",
    error: null,
    retrying: false,
    allow_ai: true,
    created_at: "2026-11-13T10:00:00Z",
    updated_at: "2026-11-13T10:00:00Z",
    ...overrides,
  };
}

function aResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    chunk_id: "c1",
    material_id: "mat1",
    material_title: "CH03 slides",
    original_filename: "CH03.pptx",
    page_number: 3,
    page_title: "User authentication",
    position: 0,
    text: "Passwords are salted and hashed.",
    snippet: [
      { text: "Passwords", highlight: true },
      { text: " are ", highlight: false },
      { text: "salted", highlight: true },
      { text: " and hashed", highlight: false },
    ],
    score: 0.03,
    vector_rank: 1,
    keyword_rank: 1,
    ...overrides,
  };
}

function serve(materials: Material[], search?: (q: string) => SearchResults) {
  return mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /sessions/active": () => null,
    "GET /modules/:id/materials": () => materials,
    "GET /modules/:id/search": ({ query }) =>
      search?.(query.get("q") ?? "") ?? { query: "", results: [], indexed_chunks: 0 },
    // Not a PDF, so the viewer shows the text (MaterialViewer.test covers PDFs).
    "GET /materials/:id": () =>
      aMaterial({
        content_type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      }),
    "GET /materials/:id/pages": () => [1, 2, 3].map((n) => aPage(n)),
    "GET /materials/:id/pages/:n": ({ params }) => ({
      ...aPage(Number(params.n)),
      text: `Text of page ${params.n}`,
    }),
  });
}

const aPage = (n: number) => ({
  page_number: n,
  title: `Slide ${n}`,
  char_count: 14,
  is_scanned: false,
});

const openTab = () => renderApp("/modules/m1?tab=materials");

test("while nothing is indexed, the box is off and says why", async () => {
  serve([aMaterial({ status: "processing" }), aMaterial({ id: "mat2", status: "uploaded" })]);
  openTab();

  expect(
    await screen.findByText("Nothing is indexed yet: 2 files still being processed."),
  ).toBeInTheDocument();
  expect(screen.getByRole("searchbox", { name: "Search materials" })).toBeDisabled();
});

test("with no materials there's no search box", async () => {
  serve([]);
  openTab();

  await screen.findByText(/No materials yet/);
  expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
});

test("hits on one page show once, with the best snippet; Markdown is hidden in snippets and titles", async () => {
  serve([aMaterial()], (q) => ({
    query: q,
    indexed_chunks: 12,
    results: [
      aResult({
        chunk_id: "best",
        material_title: "TCP notes",
        page_number: 2,
        page_title: null,
        snippet: [
          { text: "- **", highlight: false },
          { text: "Inference", highlight: true },
          { text: "** is `slow`", highlight: false },
        ],
      }),
      aResult({ chunk_id: "other", page_number: 3, page_title: "Q3 essay *(Ch5, 5 marks)*" }),
      aResult({ chunk_id: "worse", material_title: "TCP notes", page_number: 2 }),
    ],
  }));
  openTab();
  const user = userEvent.setup();

  await user.type(await screen.findByRole("searchbox", { name: "Search materials" }), "inference");
  await user.click(screen.getByRole("button", { name: "Search" }));

  const results = await screen.findByRole("list", { name: "Results for “inference”" });
  const items = within(results).getAllByRole("button");
  expect(items).toHaveLength(2);
  const [first, second] = items as [HTMLElement, HTMLElement];
  expect(first).toHaveTextContent("TCP notes · page 2");
  expect(first).toHaveTextContent("Inference is slow");
  expect(first).not.toHaveTextContent(/[*`]/);
  expect(within(first).getByText("Inference").tagName).toBe("MARK");
  expect(first).toHaveTextContent("2 matches on this page");
  expect(second).toHaveTextContent("CH03 slides · page 3 · Q3 essay (Ch5, 5 marks)");
  expect(second).not.toHaveTextContent(/[*`]/);
  expect(second).not.toHaveTextContent(/matches on this page/);
});

test("a search shows snippets with material and page; a result opens that page", async () => {
  const { calls } = serve(
    [aMaterial(), aMaterial({ id: "mat2", title: "CH04", status: "processing" })],
    (q) => ({ query: q, indexed_chunks: 12, results: [aResult()] }),
  );
  openTab();
  const user = userEvent.setup();

  expect(
    await screen.findByText("1 file still being processed isn't searched yet."),
  ).toBeInTheDocument();
  await user.type(screen.getByRole("searchbox", { name: "Search materials" }), "salted passwords");
  await user.click(screen.getByRole("button", { name: "Search" }));

  const results = await screen.findByRole("list", { name: "Results for “salted passwords”" });
  expect(calls.some((c) => c.path === "/modules/m1/search")).toBe(true);
  const item = within(results).getByRole("button", { name: /Passwords are salted/ });
  expect(within(item).getByText("Passwords").tagName).toBe("MARK");
  expect(within(item).getByText("salted").tagName).toBe("MARK");
  expect(within(item).getByText("CH03 slides · page 3").tagName).toBe("STRONG");
  expect(item).toHaveTextContent("CH03 slides · page 3 · User authentication");
  expect(item).not.toHaveTextContent("CH03.pptx");
  expect(item).not.toHaveTextContent(/matches on this page/);

  await user.click(item);
  const dialog = await screen.findByRole("dialog", { name: "CH03 slides" });
  const page = await within(dialog).findByRole("region", { name: "Page 3 text" });
  expect(await within(page).findByText("Text of page 3")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: /Page 3/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("says when nothing matches", async () => {
  serve([aMaterial()], (q) => ({ query: q, indexed_chunks: 5, results: [] }));
  openTab();
  const user = userEvent.setup();

  await user.type(await screen.findByRole("searchbox", { name: "Search materials" }), "zebra");
  await user.click(screen.getByRole("button", { name: "Search" }));

  expect(await screen.findByText("No matches for “zebra”.")).toBeInTheDocument();
});

test("says honestly when the ready files had no text to index", async () => {
  serve([aMaterial({ scanned_page_count: 3 })], (q) => ({
    query: q,
    indexed_chunks: 0,
    results: [],
  }));
  openTab();
  const user = userEvent.setup();

  await user.type(await screen.findByRole("searchbox", { name: "Search materials" }), "anything");
  await user.click(screen.getByRole("button", { name: "Search" }));

  expect(await screen.findByText(/no text layer to search/)).toBeInTheDocument();
});
