/**
 * Citations in an answer: `[S1]`, `[S2][S4]`, `[S2, S4]`, and gpt-oss's own `【S1】`
 * (it uses both, even when asked for square brackets). The API parses them the same way
 * (app/services/tutor/citations.py) to store which sources were cited.
 */

/** One pair of brackets with one or more labels: ASCII [ ] or full-width 【 】. */
export const CITATION = /[[【]\s*(S\d+(?:\s*[,;]\s*S\d+)*)\s*[\]】]/g;

/** The same, without the global flag: for "does this text cite anything?" checks. */
const HAS_CITATION = new RegExp(CITATION.source);

export type TextPart = { text: string } | { labels: string[]; raw: string };

/** The text split into plain runs and citation groups (each with its labels, in order). */
export function splitCitations(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const start = match.index;
    if (start > last) parts.push({ text: text.slice(last, start) });
    parts.push({ labels: match[1]!.match(/S\d+/g) ?? [], raw: match[0] });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

/** Every label the text cites, once each, in order of first appearance. */
export function citedLabels(text: string): string[] {
  const seen: string[] = [];
  for (const part of splitCitations(text)) {
    if ("labels" in part)
      for (const label of part.labels) if (!seen.includes(label)) seen.push(label);
  }
  return seen;
}

// --- a remark plugin: citation groups become <cite data-labels="S1 S2"> elements ---

type MdNode = {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hName?: string; hProperties?: Record<string, string>; hChildren?: unknown[] };
};

/** Nodes whose text is never a citation: code, maths, and links (their text is a link). */
const SKIP = new Set(["code", "inlineCode", "math", "inlineMath", "link", "linkReference"]);

function citationNodes(value: string): MdNode[] {
  return splitCitations(value).map((part) =>
    "text" in part
      ? { type: "text", value: part.text }
      : {
          type: "citation",
          data: {
            hName: "cite",
            hProperties: { "data-labels": part.labels.join(" "), "data-raw": part.raw },
            hChildren: [{ type: "text", value: part.raw }],
          },
        },
  );
}

function walk(node: MdNode): void {
  if (!node.children || SKIP.has(node.type)) return;
  node.children = node.children.flatMap((child) => {
    if (child.type === "text" && child.value !== undefined && HAS_CITATION.test(child.value)) {
      return citationNodes(child.value);
    }
    walk(child);
    return [child];
  });
}

/** For react-markdown's `remarkPlugins`. */
export function remarkCitations() {
  return (tree: MdNode) => walk(tree);
}
