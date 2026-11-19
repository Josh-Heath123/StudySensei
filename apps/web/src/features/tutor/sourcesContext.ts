import { createContext, useContext } from "react";

import type { SourceView } from "./turns";

export type OpenSource = (source: SourceView) => void;

/** What the citation chips inside one answer link to, and how they open the viewer. */
export const SourcesContext = createContext<{
  sources: SourceView[];
  open: OpenSource;
}>({ sources: [], open: () => undefined });

export const useAnswerSources = () => useContext(SourcesContext);

/** "CH09 · page 14" (and the page's title, when it has one). */
export function sourceLabel(source: SourceView): string {
  const base = `${source.title} · page ${source.page}`;
  return source.pageTitle ? `${base}: ${source.pageTitle}` : base;
}
