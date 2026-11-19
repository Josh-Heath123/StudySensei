import "katex/dist/katex.min.css";

import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { CitationChips } from "./CitationChip";
import { remarkCitations } from "./citations";

/**
 * An answer's Markdown, rendered safely. Loaded lazily (KaTeX is large):
 * - raw HTML is never rendered (react-markdown drops it: there's no rehype-raw);
 * - link URLs pass react-markdown's safe-protocol filter, and open in a new tab;
 * - maths ($…$, $$…$$) goes through KaTeX with \`trust: false\` (no \href, \url, \html…);
 * - citations become chips (remarkCitations), except inside code, maths and links.
 */
export default function AnswerMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      skipHtml
      remarkPlugins={[remarkGfm, remarkMath, remarkCitations]}
      rehypePlugins={[[rehypeKatex, { trust: false, strict: "ignore", throwOnError: false }]]}
      components={{
        cite: (props: ComponentProps<"cite"> & { "data-labels"?: string; "data-raw"?: string }) => (
          <CitationChips
            labels={(props["data-labels"] ?? "").split(" ").filter(Boolean)}
            raw={props["data-raw"] ?? ""}
          />
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noreferrer noopener" className="text-link underline">
            {children}
          </a>
        ),
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">{children}</table>
          </div>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
