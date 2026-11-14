import type { Material } from "./api";

export type StatusText = { text: string; tone: "muted" | "ink" | "danger" };

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** What a material's status line says, in words (never colour alone). */
export function statusText(material: Material): StatusText {
  if (material.status === "failed") return { text: `Failed: ${material.error}`, tone: "danger" };
  if (material.retrying) return { text: `Retrying: ${material.error}`, tone: "muted" };
  if (material.status === "processing") {
    // Pages are counted by extraction; indexing for search comes after.
    const text = material.page_count === null ? "Extracting text…" : "Indexing for search…";
    return { text, tone: "muted" };
  }
  if (material.status === "uploaded") return { text: "Waiting to be processed…", tone: "muted" };
  const scanned = material.scanned_page_count ?? 0;
  const pages = material.page_count ?? 0;
  if (scanned > 0) {
    return { text: `Ready · ${scanned} of ${plural(pages, "page")} scanned`, tone: "ink" };
  }
  return { text: "Ready", tone: "ink" };
}

/** Page and scanned-page counts for the details line, once known. */
export function pageDetails(material: Material): string[] {
  if (material.page_count === null) return [];
  const details = [plural(material.page_count, "page")];
  if (material.scanned_page_count) details.push(`${material.scanned_page_count} scanned`);
  return details;
}
