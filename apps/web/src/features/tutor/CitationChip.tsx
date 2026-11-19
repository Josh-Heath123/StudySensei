import { plainText } from "@/features/modules/materials/searchResults";
import { Tooltip } from "@/ui/tooltip";

import { sourceLabel, useAnswerSources } from "./sourcesContext";

/**
 * One citation group from an answer (`[S1]`, `[S2, S4]`, `【S1】`): a small violet chip per
 * label. Hovering or focusing one names the material and page; clicking opens the viewer
 * there. A label that wasn't among the answer's sources stays plain text, as written.
 */
export function CitationChips({ labels, raw }: { labels: string[]; raw: string }) {
  const { sources, open } = useAnswerSources();
  const found = labels.map((label) => sources.find((s) => s.label === label));
  if (found.every((source) => source === undefined)) return <>{raw}</>;
  return (
    <>
      {labels.map((label, index) => {
        const source = found[index];
        if (!source) return <span key={label}>[{label}]</span>;
        const name = plainText(sourceLabel(source));
        const chip = (
          <button
            type="button"
            disabled={source.materialId === null}
            onClick={() => open(source)}
            aria-label={`Source ${label}: ${name}`}
            className="bg-accent-soft text-link hover:bg-primary focus-visible:bg-primary mx-0.5 inline-flex h-5 cursor-pointer items-center rounded-sm px-1.5 align-[0.1em] text-[11px] leading-none font-semibold tabular-nums transition-colors hover:text-white focus-visible:text-white disabled:cursor-default disabled:opacity-60"
          >
            {label}
          </button>
        );
        return (
          <Tooltip key={label} label={source.materialId === null ? `${name} (deleted)` : name}>
            {chip}
          </Tooltip>
        );
      })}
    </>
  );
}
