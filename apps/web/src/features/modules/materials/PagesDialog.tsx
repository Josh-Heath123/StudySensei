import { useState } from "react";

import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import { usePage, usePages, type Material } from "./api";

/**
 * The extracted text of a material, a page at a time, as plain text. A placeholder
 * for the pdf.js viewer that comes later; it shows what the chunker will read.
 */
export function PagesDialog({
  material,
  initialPage,
  onClose,
}: {
  material: Pick<Material, "id" | "title">;
  /** The page to open at (from a search result); the first page otherwise. */
  initialPage?: number;
  onClose: () => void;
}) {
  const pages = usePages(material.id);
  const [chosen, setChosen] = useState<number | null>(initialPage ?? null);
  const current = chosen ?? pages.data?.[0]?.page_number ?? null;
  const page = usePage(material.id, current);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{material.title}</DialogTitle>
          <DialogDescription>
            Extracted text, as the search and tutor will read it.
          </DialogDescription>
        </DialogHeader>
        {pages.isPending && <p className="text-muted text-sm">Loading…</p>}
        {pages.isError && (
          <p role="alert" className="text-danger text-sm">
            {pages.error.message}
          </p>
        )}
        {pages.data && pages.data.length === 0 && (
          <p className="text-muted text-sm">No text has been extracted yet.</p>
        )}
        {pages.data && pages.data.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
            <nav aria-label="Pages" className="max-h-[60vh] overflow-y-auto">
              <ol className="grid gap-1">
                {pages.data.map((p) => (
                  <li key={p.page_number}>
                    <button
                      type="button"
                      aria-current={p.page_number === current ? "page" : undefined}
                      onClick={() => setChosen(p.page_number)}
                      className={cn(
                        "w-full rounded-md px-2 py-1.5 text-left text-sm",
                        p.page_number === current ? "bg-ink text-paper" : "hover:bg-surface",
                      )}
                    >
                      <span className="tabular font-semibold">Page {p.page_number}</span>
                      {p.title && <span className="block truncate text-xs">{p.title}</span>}
                      {p.is_scanned && <span className="block text-xs">Scanned</span>}
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
            <section
              aria-label={current ? `Page ${current} text` : "Page text"}
              className="min-w-0"
            >
              {page.isPending && <p className="text-muted text-sm">Loading…</p>}
              {page.data &&
                (page.data.is_scanned && page.data.char_count === 0 ? (
                  <p className="text-muted text-sm">
                    No text on this page. It looks scanned or is a picture; a later step will read
                    it from the image.
                  </p>
                ) : (
                  <>
                    {page.data.is_scanned && (
                      <p className="text-muted mb-2 text-xs">
                        Very little text: this page will also be read from its image later.
                      </p>
                    )}
                    <pre className="border-line max-h-[60vh] overflow-y-auto rounded-md border-2 p-4 font-sans text-sm whitespace-pre-wrap">
                      {page.data.text}
                    </pre>
                    <p className="text-muted mt-1 text-xs">{page.data.char_count} characters</p>
                  </>
                ))}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
