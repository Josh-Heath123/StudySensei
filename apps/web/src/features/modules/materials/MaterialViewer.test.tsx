import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { vi } from "vitest";

import { mockApi } from "@/test/mockApi";

import { MaterialViewer, type ViewedMaterial } from "./MaterialViewer";
import { PdfRenderCancelled, openPdf, type PdfDocument } from "./pdf";

// pdf.js at the module boundary: jsdom has no canvas.
vi.mock("./pdf", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./pdf")>();
  return { ...actual, openPdf: vi.fn() };
});
const open = vi.mocked(openPdf);

type Drawn = { page: number; width: number; cancelled: boolean };

/** A fake document: records each render; `pending` renders never finish. */
function aPdf({ numPages = 4, pending = false, fails = false } = {}) {
  const drawn: Drawn[] = [];
  const doc: PdfDocument = {
    numPages,
    destroy: vi.fn(),
    render: (page, _canvas, width) => {
      const entry = { page, width, cancelled: false };
      drawn.push(entry);
      let reject: (err: unknown) => void = () => {};
      const promise = new Promise<void>((resolve, rej) => {
        reject = rej;
        if (fails) rej(new Error("bad page"));
        else if (!pending) resolve();
      });
      return {
        promise,
        cancel: () => {
          entry.cancelled = true;
          reject(new PdfRenderCancelled());
        },
      };
    },
  };
  return { doc, drawn };
}

const PDF: ViewedMaterial = { id: "mat1", title: "CH03 slides", content_type: "application/pdf" };
const DECK: ViewedMaterial = { ...PDF, content_type: "application/vnd.ms-powerpoint" };

function serveText() {
  return mockApi({
    "GET /materials/:id/pages/:n": ({ params }) => ({
      page_number: Number(params.n),
      title: null,
      text: `Text of page ${params.n}`,
      char_count: 14,
      is_scanned: false,
    }),
  });
}

/** The viewer with its page held in state, as PagesDialog holds it. */
function renderViewer(material: ViewedMaterial, { page = 1, pageCount = 4 } = {}) {
  function Harness() {
    const [current, setCurrent] = useState(page);
    return (
      <MaterialViewer
        material={material}
        page={current}
        pageCount={pageCount}
        onPageChange={setCurrent}
      />
    );
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

afterEach(() => open.mockReset());

test("a PDF is opened once and drawn page by page with every kind of navigation", async () => {
  const { doc, drawn } = aPdf();
  open.mockResolvedValue(doc);
  const user = renderViewer(PDF, { page: 2 });

  await waitFor(() => expect(drawn.map((d) => d.page)).toEqual([2]));
  expect(screen.getByText("Page 2 of 4")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Page 2 of CH03 slides" })).toBeInTheDocument();
  expect(drawn[0]!.width).toBeGreaterThan(0);

  await user.click(screen.getByRole("button", { name: "Next page" }));
  await user.keyboard("{ArrowRight}");
  await waitFor(() => expect(screen.getByText("Page 4 of 4")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();

  await user.keyboard("{ArrowLeft}");
  const box = screen.getByLabelText("Go to page");
  await user.clear(box);
  await user.type(box, "1{Enter}");
  await waitFor(() => expect(screen.getByText("Page 1 of 4")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

  // Out of range jumps are clamped.
  await user.clear(screen.getByLabelText("Go to page"));
  await user.type(screen.getByLabelText("Go to page"), "99{Enter}");
  await waitFor(() => expect(screen.getByText("Page 4 of 4")).toBeInTheDocument());

  expect(drawn.map((d) => d.page)).toEqual([2, 3, 4, 3, 1, 4]);
  expect(open).toHaveBeenCalledTimes(1);
  expect(open.mock.calls[0]![0]).toMatch(/\/materials\/mat1\/file$/);
});

test("changing page cancels a drawing still in flight", async () => {
  const { doc, drawn } = aPdf({ pending: true });
  open.mockResolvedValue(doc);
  const user = renderViewer(PDF);
  await waitFor(() => expect(drawn).toHaveLength(1));

  await user.click(screen.getByRole("button", { name: "Next page" }));

  await waitFor(() => expect(drawn).toHaveLength(2));
  expect(drawn[0]).toMatchObject({ page: 1, cancelled: true });
  expect(drawn[1]).toMatchObject({ page: 2, cancelled: false });
  expect(screen.queryByText(/Couldn't show the PDF/)).not.toBeInTheDocument();
});

test("a PDF that won't load falls back to its extracted text", async () => {
  serveText();
  open.mockRejectedValue(new Error("Invalid PDF structure"));
  const user = renderViewer(PDF, { page: 3 });

  expect(await screen.findByText(/Couldn't show the PDF itself/)).toBeInTheDocument();
  const text = await screen.findByRole("region", { name: "Page 3 text" });
  expect(text).toHaveTextContent("Text of page 3");

  await user.keyboard("{ArrowRight}");
  expect(await screen.findByText("Text of page 4")).toBeInTheDocument();
});

test("a page that won't draw falls back to text too", async () => {
  serveText();
  open.mockResolvedValue(aPdf({ fails: true }).doc);
  renderViewer(PDF);

  expect(await screen.findByText(/Couldn't show the PDF itself/)).toBeInTheDocument();
  expect(await screen.findByText("Text of page 1")).toBeInTheDocument();
});

test("other kinds show their extracted text, with the same navigation", async () => {
  serveText();
  const user = renderViewer(DECK, { pageCount: 2 });

  expect(await screen.findByText("Text of page 1")).toBeInTheDocument();
  expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Next page" }));

  expect(await screen.findByText("Text of page 2")).toBeInTheDocument();
  expect(open).not.toHaveBeenCalled();
  expect(screen.queryByText(/Couldn't show the PDF/)).not.toBeInTheDocument();
});
