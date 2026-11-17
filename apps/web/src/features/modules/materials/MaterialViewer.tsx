import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { materialFileUrl, usePage } from "./api";
import { openPdf, PdfRenderCancelled, type PdfDocument } from "./pdf";

export type ViewedMaterial = {
  id: string;
  title: string;
  /** Unknown while it loads; only "application/pdf" is drawn, the rest shows its text. */
  content_type?: string;
};

const PDF = "application/pdf";

/**
 * One page of a material: a PDF drawn with pdf.js (fit to the width, sharp at the device
 * pixel ratio), anything else as its extracted text. Previous / next, a page box, the ←/→
 * keys and "Page N of M" work for both. A PDF that won't load or draw falls back to text.
 */
export function MaterialViewer({
  material,
  page,
  pageCount,
  onPageChange,
}: {
  material: ViewedMaterial;
  page: number;
  /** Extracted pages; a PDF not extracted yet uses its own page count. */
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  const isPdf = material.content_type === PDF;
  const pdf = usePdf(isPdf ? material.id : null);
  const [drawFailed, setDrawFailed] = useState(false);
  const total = Math.max(pageCount, pdf.doc?.numPages ?? 0);
  const asText = !isPdf || pdf.failed || drawFailed;

  const go = (target: number) => {
    const clamped = Math.min(Math.max(1, target), Math.max(1, total));
    if (clamped !== page) onPageChange(clamped);
  };
  const goRef = useRef(go);
  useEffect(() => {
    goRef.current = go;
  });

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (event.key === "ArrowLeft") goRef.current(page - 1);
      else if (event.key === "ArrowRight") goRef.current(page + 1);
      else return;
      event.preventDefault();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [page]);

  return (
    <div className="grid min-w-0 gap-3">
      <PageNav page={page} total={total} onGo={go} />
      {material.content_type === undefined ? (
        <p className="text-muted text-sm">Loading…</p>
      ) : asText ? (
        <>
          {isPdf && (
            <p role="status" className="text-warning text-sm">
              Couldn't show the PDF itself, so this is its extracted text.
            </p>
          )}
          <PageText materialId={material.id} page={page} />
        </>
      ) : pdf.doc ? (
        <PdfPage
          doc={pdf.doc}
          page={page}
          label={`Page ${page} of ${material.title}`}
          onError={() => setDrawFailed(true)}
        />
      ) : (
        <p className="text-muted text-sm">Loading the PDF…</p>
      )}
    </div>
  );
}

function PageNav({
  page,
  total,
  onGo,
}: {
  page: number;
  total: number;
  onGo: (n: number) => void;
}) {
  return (
    <nav aria-label="Page navigation" className="flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        size="icon-sm"
        aria-label="Previous page"
        disabled={page <= 1}
        onClick={() => onGo(page - 1)}
      >
        <ChevronLeft aria-hidden />
      </Button>
      <Button
        variant="outline"
        size="icon-sm"
        aria-label="Next page"
        disabled={total === 0 || page >= total}
        onClick={() => onGo(page + 1)}
      >
        <ChevronRight aria-hidden />
      </Button>
      {/* Keyed by page so the box shows the current page after any navigation. */}
      <JumpForm key={page} page={page} total={total} onGo={onGo} />
      <span className="tabular text-sm" aria-live="polite">
        {total > 0 ? `Page ${page} of ${total}` : `Page ${page}`}
      </span>
    </nav>
  );
}

function JumpForm({
  page,
  total,
  onGo,
}: {
  page: number;
  total: number;
  onGo: (n: number) => void;
}) {
  const [value, setValue] = useState(String(page));

  function submit(event: FormEvent) {
    event.preventDefault();
    const n = Number.parseInt(value, 10);
    if (Number.isFinite(n)) onGo(n);
    else setValue(String(page));
  }

  return (
    <form onSubmit={submit} noValidate className="flex items-center gap-1">
      <Input
        aria-label="Go to page"
        type="number"
        inputMode="numeric"
        min={1}
        max={total || undefined}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="tabular w-20"
      />
      <Button type="submit" variant="ghost" size="sm">
        Go
      </Button>
    </form>
  );
}

/** The PDF, opened once per material (not per page), and closed when it changes. */
function usePdf(materialId: string | null) {
  const [state, setState] = useState<{ id: string; doc: PdfDocument | null; failed: boolean }>({
    id: "",
    doc: null,
    failed: false,
  });

  useEffect(() => {
    if (materialId === null) return;
    let live = true;
    let opened: PdfDocument | null = null;
    openPdf(materialFileUrl(materialId)).then(
      (doc) => {
        if (live) {
          opened = doc;
          setState({ id: materialId, doc, failed: false });
        } else {
          doc.destroy();
        }
      },
      () => live && setState({ id: materialId, doc: null, failed: true }),
    );
    return () => {
      live = false;
      opened?.destroy();
    };
  }, [materialId]);

  // A previous material's document is never shown for this one.
  return state.id === materialId ? state : { doc: null, failed: false };
}

function PdfPage({
  doc,
  page,
  label,
  onError,
}: {
  doc: PdfDocument;
  page: number;
  label: string;
  onError: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  const [drawing, setDrawing] = useState(true);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onErrorRef.current = onError;
  });

  // Fit to the width, and follow it when the dialog or window resizes.
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const measure = () => setWidth(Math.floor(element.clientWidth) || 800);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Draw; a new page or width cancels the drawing in flight.
  useEffect(() => {
    if (!width || !canvas.current) return;
    setDrawing(true);
    const task = doc.render(page, canvas.current, width);
    task.promise.then(
      () => setDrawing(false),
      (err: unknown) => {
        if (!(err instanceof PdfRenderCancelled)) onErrorRef.current();
      },
    );
    return () => task.cancel();
  }, [doc, page, width]);

  return (
    <section aria-label={`Page ${page}`} aria-busy={drawing} className="min-w-0">
      <div
        ref={box}
        className="border-line relative max-h-[70vh] overflow-y-auto rounded-md border-2 bg-white"
      >
        <canvas ref={canvas} role="img" aria-label={label} className="block" />
        {drawing && (
          <p className="text-muted bg-paper/80 absolute top-2 left-2 rounded px-2 py-1 text-xs">
            Drawing page {page}…
          </p>
        )}
      </div>
    </section>
  );
}

/** A page's extracted text: what the search and tutor read. */
function PageText({ materialId, page }: { materialId: string; page: number }) {
  const text = usePage(materialId, page);

  return (
    <section aria-label={`Page ${page} text`} className="min-w-0">
      {text.isPending && <p className="text-muted text-sm">Loading…</p>}
      {text.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load page {page}: {text.error.message}
        </p>
      )}
      {text.data &&
        (text.data.is_scanned && text.data.char_count === 0 ? (
          <p className="text-muted text-sm">
            No text on this page. It looks scanned or is a picture; a later step will read it from
            the image.
          </p>
        ) : (
          <>
            <pre className="border-line max-h-[70vh] overflow-y-auto rounded-md border-2 p-4 font-sans text-sm whitespace-pre-wrap">
              {text.data.text}
            </pre>
            <p className="text-muted mt-1 text-xs">{text.data.char_count} characters</p>
          </>
        ))}
    </section>
  );
}
