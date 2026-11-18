import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { materialFileUrl, usePage } from "./api";
import { openPdf, PdfRenderCancelled, type PdfDocument, type PdfFit } from "./pdf";

export type ViewedMaterial = {
  id: string;
  title: string;
  /** Unknown while it loads; only "application/pdf" is drawn, the rest shows its text. */
  content_type?: string;
};

const PDF = "application/pdf";

/** "page": the whole page in view (the default); "width": the page as wide as the box, scrolling down. */
type Fit = "page" | "width";

/**
 * One page of a material: a PDF drawn with pdf.js (the whole page fitted into view by default,
 * or fitted to the width; sharp at the device pixel ratio), anything else as its extracted
 * text. Previous / next, a page box, the ←/→ keys and "Page N of M" work for both. A PDF that
 * won't load or draw falls back to text.
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
  const [fit, setFit] = useState<Fit>("page");
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
      <PageNav
        page={page}
        total={total}
        onGo={go}
        fit={pdf.doc && !asText ? fit : undefined}
        onFit={setFit}
      />
      {material.content_type === undefined ? (
        <PageSkeleton label="Loading…" />
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
          fit={fit}
          onError={() => setDrawFailed(true)}
        />
      ) : (
        <PageSkeleton label="Loading the PDF…" />
      )}
    </div>
  );
}

function PageNav({
  page,
  total,
  onGo,
  fit,
  onFit,
}: {
  page: number;
  total: number;
  onGo: (n: number) => void;
  /** Shown only while a PDF page is drawn. */
  fit?: Fit;
  onFit: (fit: Fit) => void;
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
      {fit && <FitToggle fit={fit} onFit={onFit} />}
      <span className="tabular ml-auto text-sm font-medium" aria-live="polite">
        {total > 0 ? `Page ${page} of ${total}` : `Page ${page}`}
      </span>
    </nav>
  );
}

/** Fit page / Fit width, as a two-segment control (docs/DESIGN.md "Segmented control"). */
function FitToggle({ fit, onFit }: { fit: Fit; onFit: (fit: Fit) => void }) {
  const options: { value: Fit; label: string }[] = [
    { value: "page", label: "Fit page" },
    { value: "width", label: "Fit width" },
  ];
  return (
    <div role="group" aria-label="Zoom" className="bg-subtle flex gap-1 rounded-[12px] p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={fit === option.value}
          onClick={() => onFit(option.value)}
          className={cn(
            "min-h-8 cursor-pointer rounded-[9px] px-3 text-sm font-semibold transition-[background-color,color,box-shadow]",
            fit === option.value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
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
        className="tabular min-h-9 w-20 py-1 text-sm"
      />
      <Button type="submit" variant="outline" size="sm">
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
  fit,
  onError,
}: {
  doc: PdfDocument;
  page: number;
  label: string;
  fit: Fit;
  onError: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  // What was last drawn completely: busy is derived from it, so a new page, zoom or size is
  // busy from its very first render. (A `drawing` flag set in the effect was still false for
  // one commit after a page change, which let readers see "drawn" before the canvas was.)
  const [drawn, setDrawn] = useState<string | null>(null);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onErrorRef.current = onError;
  });

  // Measure the box, and follow it when the dialog or window resizes. In "page" mode the box
  // has a fixed height and never scrolls; in "width" mode its scrollbar space is reserved, so
  // drawing a taller page never changes the width it was drawn for.
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const measure = () => {
      const width = Math.floor(element.clientWidth) || 800;
      const height = Math.floor(element.clientHeight) || 600;
      setSize((old) => (old?.width === width && old.height === height ? old : { width, height }));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const target: PdfFit | null = size
    ? fit === "page"
      ? { width: size.width, height: size.height }
      : { width: size.width }
    : null;
  const key = target ? `${page}:${fit}:${target.width}x${target.height ?? "auto"}` : null;
  const busy = key === null || drawn !== key;

  // Draw; a new page, zoom or size cancels the drawing in flight.
  useEffect(() => {
    if (!target || !key || !canvas.current) return;
    const task = doc.render(page, canvas.current, target);
    task.promise.then(
      () => setDrawn(key),
      (err: unknown) => {
        if (!(err instanceof PdfRenderCancelled)) onErrorRef.current();
      },
    );
    return () => task.cancel();
    // `key` stands for `target` (a new object every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, page, key]);

  return (
    <section aria-label={`Page ${page}`} aria-busy={busy} className="min-w-0">
      <div
        ref={box}
        data-fit={fit}
        className={cn(
          "bg-surface border-line relative rounded-lg border shadow-sm",
          fit === "page"
            ? "flex h-[min(64vh,calc(100dvh-18rem))] min-h-64 items-center justify-center overflow-hidden"
            : "max-h-[64vh] [scrollbar-gutter:stable] overflow-y-auto",
        )}
      >
        <canvas ref={canvas} role="img" aria-label={label} className="block" />
        {busy && (
          <p className="text-muted bg-surface border-line absolute top-3 left-3 rounded-sm border px-2 py-1 text-xs shadow-sm">
            Drawing page {page}…
          </p>
        )}
      </div>
    </section>
  );
}

function PageText({ materialId, page }: { materialId: string; page: number }) {
  const text = usePage(materialId, page);

  return (
    <section aria-label={`Page ${page} text`} className="min-w-0">
      {text.isPending && <PageSkeleton label="Loading…" />}
      {text.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load page {page}: {text.error.message}
        </p>
      )}
      {text.data &&
        (text.data.is_scanned && text.data.char_count === 0 ? (
          <p className="bg-surface border-line text-muted rounded-lg border p-5 text-sm shadow-sm">
            No text on this page. It looks scanned or is a picture; a later step will read it from
            the image.
          </p>
        ) : (
          <>
            <pre className="bg-surface border-line text-fg max-h-[70vh] overflow-y-auto rounded-lg border p-5 font-sans text-sm leading-relaxed whitespace-pre-wrap shadow-sm sm:p-6">
              {text.data.text}
            </pre>
            <p className="text-muted tabular mt-2 text-xs">{text.data.char_count} characters</p>
          </>
        ))}
    </section>
  );
}

/** A page-shaped placeholder on the solid page surface, while the page or the PDF loads. */
function PageSkeleton({ label }: { label: string }) {
  return (
    <div
      aria-busy="true"
      className="bg-surface border-line grid gap-3 rounded-lg border p-5 shadow-sm sm:p-6"
    >
      <p className="sr-only">{label}</p>
      <div aria-hidden className="skeleton h-5 w-1/2" />
      <div aria-hidden className="skeleton h-3 w-full" />
      <div aria-hidden className="skeleton h-3 w-11/12" />
      <div aria-hidden className="skeleton h-3 w-4/5" />
      <div aria-hidden className="skeleton h-3 w-2/3" />
    </div>
  );
}
