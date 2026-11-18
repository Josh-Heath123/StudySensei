import { useState } from "react";

import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import { useMaterial, usePages } from "./api";
import { MaterialViewer, type ViewedMaterial } from "./MaterialViewer";
import { plainText } from "./searchResults";

/**
 * The one way to read a material's pages: the page list down the side and the viewer
 * (a PDF as itself, anything else as its extracted text). Every entry point (Materials
 * rows, search results, a topic's linked pages) opens it at the right page.
 */
export function PagesDialog({
  material,
  initialPage,
  onClose,
}: {
  /** Without a content type, it's looked up. */
  material: ViewedMaterial;
  /** The page to open at (a search result, a linked page); the first page otherwise. */
  initialPage?: number;
  onClose: () => void;
}) {
  const pages = usePages(material.id);
  const details = useMaterial(material.id, material.content_type === undefined);
  const contentType = material.content_type ?? details.data?.content_type;
  const isPdf = contentType === "application/pdf";
  const [chosen, setChosen] = useState<number | null>(initialPage ?? null);
  const current = chosen ?? pages.data?.[0]?.page_number ?? 1;
  const summary = pages.data?.find((p) => p.page_number === current);
  const empty = pages.data?.length === 0;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>{material.title}</DialogTitle>
          <DialogDescription>
            {isPdf
              ? "The PDF as it was uploaded. Use ← and → to turn pages."
              : "Extracted text, as the search and tutor will read it. Use ← and → to turn pages."}
          </DialogDescription>
        </DialogHeader>
        {(pages.isPending || (contentType === undefined && details.isPending)) && (
          <div aria-busy="true" className="grid gap-4 sm:grid-cols-[180px_minmax(0,1fr)]">
            <p className="sr-only">Loading…</p>
            <div aria-hidden className="hidden gap-1.5 sm:grid sm:content-start">
              {[0, 1, 2, 3].map((n) => (
                <div key={n} className="skeleton h-11" />
              ))}
            </div>
            <div aria-hidden className="grid content-start gap-3">
              <div className="skeleton h-9 w-64 max-w-full" />
              <div className="skeleton h-[40vh] rounded-lg" />
            </div>
          </div>
        )}
        {(pages.isError || details.isError) && (
          <p role="alert" className="text-danger text-sm">
            {(pages.error ?? details.error)?.message}
          </p>
        )}
        {empty && !isPdf && contentType !== undefined && (
          <p className="text-muted text-sm">No text has been extracted yet.</p>
        )}
        {pages.data && contentType !== undefined && (!empty || isPdf) && (
          <div className={cn("grid gap-4", !empty && "sm:grid-cols-[180px_minmax(0,1fr)]")}>
            {!empty && (
              <nav
                aria-label="Pages"
                className="-mx-1 max-h-[30vh] overflow-y-auto px-1 py-1 sm:max-h-[70vh]"
              >
                <ol className="grid gap-1">
                  {pages.data.map((p) => (
                    <li key={p.page_number}>
                      <button
                        type="button"
                        aria-current={p.page_number === current ? "page" : undefined}
                        onClick={() => setChosen(p.page_number)}
                        className={cn(
                          "w-full cursor-pointer rounded-md px-3 py-2 text-left text-sm transition-colors",
                          p.page_number === current
                            ? "bg-accent-soft text-fg font-semibold"
                            : "text-fg hover:bg-subtle",
                        )}
                      >
                        <span className="tabular font-semibold">Page {p.page_number}</span>
                        {p.title && (
                          <span className="text-muted block truncate text-xs font-normal">
                            {plainText(p.title)}
                          </span>
                        )}
                        {p.is_scanned && (
                          <span className="text-muted block text-xs font-normal">Scanned</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ol>
              </nav>
            )}
            <div className="min-w-0">
              <MaterialViewer
                material={{ ...material, content_type: contentType }}
                page={current}
                pageCount={pages.data.length}
                onPageChange={setChosen}
              />
              {summary?.is_scanned && (
                <p className="text-muted mt-2 text-xs">
                  Very little text on this page: it will also be read from its image later.
                </p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
