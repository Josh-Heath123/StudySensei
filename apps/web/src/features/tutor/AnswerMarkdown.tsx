import "katex/dist/katex.min.css";

import { memo, type ComponentProps } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { CitationChips } from "./CitationChip";
import { remarkCitations } from "./citations";

/*
 * Defined once, outside any render: react-markdown treats each entry as a component type,
 * so a fresh object (or fresh arrow functions) on every render would remount every chip,
 * link and table each time the answer re-rendered (the session timer ticks every second).
 */
const REMARK = [remarkGfm, remarkMath, remarkCitations];
const REHYPE: ComponentProps<typeof ReactMarkdown>["rehypePlugins"] = [
  [rehypeKatex, { trust: false, strict: "ignore", throwOnError: false }],
];

function Cite(props: ComponentProps<"cite"> & { "data-labels"?: string; "data-raw"?: string }) {
  return (
    <CitationChips
      labels={(props["data-labels"] ?? "").split(" ").filter(Boolean)}
      raw={props["data-raw"] ?? ""}
    />
  );
}

function Link({ href, children }: ComponentProps<"a">) {
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className="text-link underline">
      {children}
    </a>
  );
}

/** Wide tables scroll sideways in their own box, each column at least readable. */
function Table({ children }: ComponentProps<"table">) {
  return (
    <div
      role="region"
      aria-label="Table"
      tabIndex={0}
      className="answer-table my-3 overflow-x-auto"
    >
      <table className="w-max min-w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

const COMPONENTS = { cite: Cite, a: Link, table: Table } as Components;

/**
 * An answer's Markdown, rendered safely. Loaded lazily (KaTeX is large):
 * - raw HTML is never rendered (react-markdown drops it: there's no rehype-raw);
 * - link URLs pass react-markdown's safe-protocol filter, and open in a new tab;
 * - maths ($…$, $$…$$) goes through KaTeX with `trust: false` (no \href, \url, \html…);
 * - citations become chips (remarkCitations), except inside code, maths and links.
 * Memoised on its text: an unchanged answer isn't parsed again.
 */
function AnswerMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown skipHtml remarkPlugins={REMARK} rehypePlugins={REHYPE} components={COMPONENTS}>
      {text}
    </ReactMarkdown>
  );
}

export default memo(AnswerMarkdown);
