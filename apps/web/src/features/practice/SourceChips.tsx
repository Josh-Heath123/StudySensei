import { useState } from "react";

import { PagesDialog } from "@/features/modules/materials/PagesDialog";
import { Tooltip, TooltipProvider } from "@/ui/tooltip";

import type { PracticeItem } from "./api";
import { sourceChip } from "./practiceText";

type Page = PracticeItem["pages"][number];

/** An item's cited pages as "CH05 p14" chips; each opens the material at its page. */
export function SourceChips({ item }: { item: Pick<PracticeItem, "pages" | "sources_missing"> }) {
  const [open, setOpen] = useState<Page | null>(null);
  if (item.pages.length === 0) {
    return item.sources_missing ? (
      <p className="text-muted text-xs">Its source was deleted.</p>
    ) : null;
  }
  return (
    <TooltipProvider>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted text-xs">From</span>
        {item.pages.map((page) => (
          <Tooltip
            key={`${page.material_id}-${page.page_number}`}
            label={`${page.material_title}, page ${page.page_number}`}
          >
            <button
              type="button"
              onClick={() => setOpen(page)}
              aria-label={`Open ${page.material_title} at page ${page.page_number}`}
              className="bg-accent-soft text-link hover:bg-primary focus-visible:bg-primary inline-flex h-6 cursor-pointer items-center rounded-sm px-2 text-xs font-semibold tabular-nums transition-colors hover:text-white focus-visible:text-white"
            >
              {sourceChip(page.material_title, page.page_number)}
            </button>
          </Tooltip>
        ))}
        {open && (
          <PagesDialog
            material={{ id: open.material_id, title: open.material_title }}
            initialPage={open.page_number}
            onClose={() => setOpen(null)}
          />
        )}
      </div>
    </TooltipProvider>
  );
}
