import { Search } from "lucide-react";
import { Fragment, useState, type FormEvent } from "react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { useSearch, type Material, type SearchResult } from "./api";
import { PagesDialog } from "./PagesDialog";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * A plain search box over the module's indexed materials. Each result opens the page
 * text at its page. Until something is indexed, it says so instead of searching.
 */
export function MaterialSearch({
  moduleId,
  materials,
}: {
  moduleId: string;
  materials: Material[];
}) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<SearchResult | null>(null);
  const search = useSearch(moduleId, query);

  const ready = materials.filter((m) => m.status === "ready").length;
  const pending = materials.filter((m) => m.status === "uploaded" || m.status === "processing");
  const searchable = ready > 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuery(draft.trim());
  }

  return (
    <section aria-label="Search materials" className="mb-8">
      <form role="search" onSubmit={submit} className="flex gap-2">
        <Input
          type="search"
          aria-label="Search materials"
          placeholder={searchable ? "Search your materials" : "Search opens once a file is indexed"}
          value={draft}
          disabled={!searchable}
          maxLength={500}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button type="submit" variant="outline" disabled={!searchable || !draft.trim()}>
          <Search aria-hidden />
          Search
        </Button>
      </form>

      {!searchable && (
        <p className="text-muted mt-2 text-sm">
          {pending.length > 0
            ? `Nothing is indexed yet: ${plural(pending.length, "file")} still being processed.`
            : "Nothing is indexed yet. Upload a file and search works once it's ready."}
        </p>
      )}
      {searchable && pending.length > 0 && (
        <p className="text-muted mt-2 text-sm">
          {plural(pending.length, "file")} still being processed{" "}
          {pending.length === 1 ? "isn't" : "aren't"} searched yet.
        </p>
      )}

      {query && search.isPending && <p className="text-muted mt-4 text-sm">Searching…</p>}
      {search.isError && (
        <p role="alert" className="text-danger mt-4 text-sm">
          {search.error.message}
        </p>
      )}
      {search.data && search.data.indexed_chunks === 0 && (
        <p className="text-muted mt-4 text-sm">
          Nothing is indexed yet: the ready files have no text layer to search. A later step will
          read scanned pages.
        </p>
      )}
      {search.data && search.data.indexed_chunks > 0 && search.data.results.length === 0 && (
        <p className="text-muted mt-4 text-sm">No matches for “{search.data.query}”.</p>
      )}
      {search.data && search.data.results.length > 0 && (
        <ol
          aria-label={`Results for “${search.data.query}”`}
          className="divide-line border-line mt-4 divide-y border-y"
        >
          {search.data.results.map((result) => (
            <li key={result.chunk_id}>
              <button
                type="button"
                onClick={() => setOpen(result)}
                className="hover:bg-surface w-full px-2 py-3 text-left"
              >
                <p className="text-sm">
                  {result.snippet.map((part, index) =>
                    part.highlight ? (
                      <mark key={index} className="bg-surface text-ink rounded-sm font-semibold">
                        {part.text}
                      </mark>
                    ) : (
                      <Fragment key={index}>{part.text}</Fragment>
                    ),
                  )}
                </p>
                <p className="text-muted mt-1 text-xs">
                  <span>{result.original_filename}</span>
                  <span className="tabular"> · Page {result.page_number}</span>
                  {result.page_title && <span> · {result.page_title}</span>}
                </p>
              </button>
            </li>
          ))}
        </ol>
      )}

      {open && (
        <PagesDialog
          material={{ id: open.material_id, title: open.material_title }}
          initialPage={open.page_number}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  );
}
