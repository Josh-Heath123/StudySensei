/**
 * The one place that touches pdf.js (pdfjs-dist, Apache-2.0). It's loaded on first use,
 * so it stays out of the main bundle, and its worker is set up the Vite way. Tests mock
 * this module: jsdom has no canvas.
 */

import type { PDFDocumentProxy } from "pdfjs-dist";

export type PdfRender = {
  /** Resolves when the page is drawn; rejects with `PdfRenderCancelled` after cancel(). */
  promise: Promise<void>;
  cancel: () => void;
};

/** The box a page is drawn into, in CSS pixels: fit its width, or the whole page when `height` is given. */
export type PdfFit = { width: number; height?: number };

export type PdfDocument = {
  numPages: number;
  /**
   * Draw page `pageNumber` (1-based) on `canvas`, scaled to `fit` (the width, or the whole
   * page inside width × height), sharp at the device pixel ratio.
   */
  render: (pageNumber: number, canvas: HTMLCanvasElement, fit: PdfFit) => PdfRender;
  destroy: () => void;
};

export class PdfRenderCancelled extends Error {
  constructor() {
    super("Rendering was cancelled");
    this.name = "PdfRenderCancelled";
  }
}

let pdfjs: Promise<typeof import("pdfjs-dist")> | null = null;

function loadPdfjs() {
  pdfjs ??= Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
  ]).then(([lib, worker]) => {
    lib.GlobalWorkerOptions.workerSrc = worker.default;
    return lib;
  });
  return pdfjs;
}

/** Open a PDF from a URL (same origin, so the session cookie goes with it). */
export async function openPdf(url: string): Promise<PdfDocument> {
  const lib = await loadPdfjs();
  const loading = lib.getDocument({ url });
  const doc: PDFDocumentProxy = await loading.promise;

  return {
    numPages: doc.numPages,
    // Destroying the loading task frees the document and its worker side.
    destroy: () => void loading.destroy(),
    render(pageNumber, canvas, fit) {
      let cancelled = false;
      let task: ReturnType<Awaited<ReturnType<typeof doc.getPage>>["render"]> | null = null;
      const promise = (async () => {
        const page = await doc.getPage(pageNumber);
        if (cancelled) throw new PdfRenderCancelled();
        const unscaled = page.getViewport({ scale: 1 });
        const byWidth = fit.width / unscaled.width;
        const scale = fit.height ? Math.min(byWidth, fit.height / unscaled.height) : byWidth;
        const viewport = page.getViewport({ scale });
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * ratio);
        canvas.height = Math.floor(viewport.height * ratio);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        task = page.render({
          canvas,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        try {
          await task.promise;
        } catch (err) {
          if (cancelled || (err instanceof Error && err.name === "RenderingCancelledException")) {
            throw new PdfRenderCancelled();
          }
          throw err;
        }
      })();
      return {
        promise,
        cancel: () => {
          cancelled = true;
          task?.cancel();
        },
      };
    },
  };
}
