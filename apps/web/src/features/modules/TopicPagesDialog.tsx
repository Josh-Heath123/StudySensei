import { Unlink } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import { useTopicPages, useUnlinkPage, type TopicNode } from "./api";
import { PagesDialog } from "./materials/PagesDialog";

/**
 * The pages linked to a topic, by material (decision 0009): how each was linked, a way
 * to read it, and Unlink for a wrong one (remembered, so relinking won't bring it back).
 */
export function TopicPagesDialog({
  moduleId,
  topic,
  onClose,
}: {
  moduleId: string;
  topic: Pick<TopicNode, "id" | "name">;
  onClose: () => void;
}) {
  const pages = useTopicPages(topic.id);
  const unlink = useUnlinkPage(moduleId, topic.id);
  const [reading, setReading] = useState<{ id: string; title: string; page: number } | null>(null);

  if (reading) {
    return (
      <PagesDialog material={reading} initialPage={reading.page} onClose={() => setReading(null)} />
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Pages for “{topic.name}”</DialogTitle>
          <DialogDescription>
            Cited pages are where the AI found the topic; similar pages read like it. Unlink a page
            that doesn't belong: it stays unlinked.
          </DialogDescription>
        </DialogHeader>
        {pages.isPending && <p className="text-muted text-sm">Loading…</p>}
        {pages.isError && (
          <p role="alert" className="text-danger text-sm">
            {pages.error.message}
          </p>
        )}
        {unlink.isError && (
          <p role="alert" className="text-danger text-sm">
            {unlink.error.message}
          </p>
        )}
        {pages.data?.length === 0 && (
          <p className="text-muted text-sm">No pages are linked to this topic yet.</p>
        )}
        <div className="max-h-[60vh] space-y-4 overflow-y-auto">
          {pages.data?.map((material) => (
            <section key={material.material_id} aria-label={material.title}>
              <h3 className="mb-1 text-sm font-semibold">{material.title}</h3>
              <ul className="grid gap-1">
                {material.pages.map((page) => (
                  <li
                    key={page.page_number}
                    className="hover:bg-surface flex items-center gap-2 rounded-md px-2 py-1"
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left text-sm"
                      onClick={() =>
                        setReading({
                          id: material.material_id,
                          title: material.title,
                          page: page.page_number,
                        })
                      }
                    >
                      <span className="tabular font-semibold">Page {page.page_number}</span>
                      {page.label && <span className="text-muted"> · {page.label}</span>}
                    </button>
                    <span className="text-muted shrink-0 text-xs">
                      {page.method === "pages"
                        ? "Cited"
                        : `Similar (${(page.score ?? 0).toFixed(2)})`}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Unlink page ${page.page_number} of ${material.title}`}
                      disabled={unlink.isPending}
                      onClick={() =>
                        unlink.mutate({
                          materialId: material.material_id,
                          pageNumber: page.page_number,
                        })
                      }
                    >
                      <Unlink aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
