import { FileText, Unlink } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import { useTopicPages, useTopicTree, useUnlinkPage, type TopicNode } from "./api";
import { EmptyState } from "./EmptyState";
import { LoadingRows } from "./LoadingRows";
import { PagesDialog } from "./materials/PagesDialog";
import { findTopic } from "./planningText";
import { TopicPlanning } from "./TopicPlanning";

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
  // The live node (it changes as confidence or workload is saved).
  const tree = useTopicTree(moduleId);
  const node = tree.data ? findTopic(tree.data, topic.id) : null;
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
          <DialogTitle>{topic.name}</DialogTitle>
          <DialogDescription>
            Your starting confidence and how long it takes, then its pages. Cited pages are where
            the AI found the topic; similar pages read like it. Unlink a page that doesn't belong:
            it stays unlinked.
          </DialogDescription>
        </DialogHeader>
        {node && <TopicPlanning moduleId={moduleId} topic={node} />}
        <h3 className="type-h3 mt-1">Pages</h3>
        {pages.isPending && <LoadingRows label="Loading pages…" rows={3} rowClassName="h-11" />}
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
          <EmptyState icon={FileText}>No pages are linked to this topic yet.</EmptyState>
        )}
        <div className="-mx-1 max-h-[60vh] space-y-5 overflow-y-auto px-1">
          {pages.data?.map((material) => (
            <section key={material.material_id} aria-label={material.title}>
              <h3 className="type-label text-muted mb-2 break-words">{material.title}</h3>
              <ul className="surface-card divide-line divide-y overflow-hidden rounded-lg">
                {material.pages.map((page) => (
                  <li
                    key={page.page_number}
                    className="hover:bg-subtle flex min-h-11 items-center gap-2 py-1 pr-1 pl-3 transition-colors"
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 cursor-pointer rounded-sm py-1.5 text-left text-sm"
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
                    <span className="text-muted tabular shrink-0 text-xs">
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
