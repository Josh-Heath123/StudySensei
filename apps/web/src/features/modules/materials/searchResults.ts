import type { SearchResult } from "./api";

export type SnippetPart = SearchResult["snippet"][number];

/**
 * Markdown syntax to hide in a snippet. Each pattern removes its whole match except the
 * groups listed in `keep`, so the words stay and only the markup goes.
 */
const RULES: { pattern: RegExp; keep: number[] }[] = [
  // ![alt](url) and [text](url): keep the alt or the text.
  { pattern: /!\[([^\]\n]*)\]\([^)\n]*\)/dg, keep: [1] },
  { pattern: /\[([^\]\n]+)\]\([^)\n]*\)/dg, keep: [1] },
  // At a line start: indentation, quote marks, then a heading, bullet or number.
  { pattern: /^[ \t]*(?:>[ \t]?)*(?:#{1,6}[ \t]+|[-*+][ \t]+|\d+[.)][ \t]+)?/dgm, keep: [] },
  // `code`, **bold**, __bold__, *italic*, _italic_ (not snake_case or 2 * 3).
  { pattern: /(`+)([^`\n]+?)\1/dg, keep: [2] },
  { pattern: /(\*\*|__)(?=\S)(.+?)(?<=\S)\1/dg, keep: [2] },
  { pattern: /\*(?=\S)([^*\n]+?)(?<=\S)\*/dg, keep: [1] },
  { pattern: /(?<!\w)_(?=\S)([^_\n]+?)(?<=\S)_(?!\w)/dg, keep: [1] },
  // A bold marker left open where the snippet was cut.
  { pattern: /\*\*+/dg, keep: [] },
];

type Char = { ch: string; highlight: boolean };

function applyRule(chars: Char[], { pattern, keep }: (typeof RULES)[number]): Char[] {
  const text = chars.map((c) => c.ch).join("");
  const drop = new Array<boolean>(chars.length).fill(false);
  for (const match of text.matchAll(pattern)) {
    const start = match.index;
    for (let i = start; i < start + match[0].length; i++) drop[i] = true;
    for (const group of keep) {
      const span = match.indices?.[group];
      if (span) for (let i = span[0]; i < span[1]; i++) drop[i] = false;
    }
  }
  return chars.filter((_, i) => !drop[i]);
}

/**
 * The snippet with Markdown syntax removed, for display. Works on the joined text, so a
 * marker split across parts still goes, and each word keeps its highlight.
 */
export function plainSnippet(parts: SnippetPart[]): SnippetPart[] {
  let chars: Char[] = parts.flatMap((part) =>
    Array.from(part.text, (ch) => ({ ch, highlight: part.highlight })),
  );
  for (const rule of RULES) chars = applyRule(chars, rule);

  const out: SnippetPart[] = [];
  for (const { ch, highlight } of chars) {
    const last = out.at(-1);
    if (last && last.highlight === highlight) last.text += ch;
    else out.push({ text: ch, highlight });
  }
  return out;
}

/** A page title (or any one-line text) with its Markdown syntax removed, for display. */
export function plainText(text: string): string {
  return plainSnippet([{ text, highlight: false }])
    .map((part) => part.text)
    .join("")
    .trim();
}

export type PageHits = { best: SearchResult; matches: number };

/**
 * One entry per (material, page), in the API's order. The first hit is the best ranked,
 * so it leads; `matches` counts every hit on that page.
 */
export function groupByPage(results: SearchResult[]): PageHits[] {
  const pages = new Map<string, PageHits>();
  for (const result of results) {
    const key = `${result.material_id}:${result.page_number}`;
    const page = pages.get(key);
    if (page) page.matches += 1;
    else pages.set(key, { best: result, matches: 1 });
  }
  return [...pages.values()];
}
