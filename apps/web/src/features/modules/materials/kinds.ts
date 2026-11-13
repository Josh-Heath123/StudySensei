import type { components } from "@/lib/api/schema";

export type MaterialKind = components["schemas"]["MaterialOut"]["kind"];

export const KIND_LABELS: Record<MaterialKind, string> = {
  slides: "Slides",
  notes: "Notes",
  study_guide: "Study guide",
  tutorial: "Tutorial",
  past_paper: "Past paper",
  test: "Test",
  assignment: "Assignment",
  outline: "Outline",
  other: "Other",
};

export const KINDS = Object.keys(KIND_LABELS) as MaterialKind[];

/** Same limits as the API (it checks again; this just answers sooner). */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
export const ALLOWED_EXTENSIONS = [
  ".pdf",
  ".pptx",
  ".docx",
  ".md",
  ".txt",
  ".png",
  ".jpg",
  ".jpeg",
];
export const ACCEPT = ALLOWED_EXTENSIONS.join(",");

// First match wins. Whole words only, so "Latest" isn't a test.
const RULES: [RegExp, MaterialKind][] = [
  [/\b(exams?|past ?papers?|papers?)\b/i, "past_paper"],
  [/\b(tests?|quiz(zes)?)\b/i, "test"],
  [/\b(assignments?|assign)\b/i, "assignment"],
  [/\b(tutorials?|tut)\b/i, "tutorial"],
  [/\bstudy ?guide\b|\bguide\b/i, "study_guide"],
  [/\b(outline|syllabus)\b/i, "outline"],
  [/\b(notes?|summary)\b/i, "notes"],
  [/\b(slides?|lecture|deck)\b/i, "slides"],
];

const extension = (filename: string) => {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot).toLowerCase() : "";
};

/** A first guess at what a file is, from its name; the student can change it. */
export function guessKind(filename: string): MaterialKind {
  const words = filename.replace(/[_\-.]+/g, " ");
  for (const [pattern, kind] of RULES) {
    if (pattern.test(words)) return kind;
  }
  const ext = extension(filename);
  if (ext === ".pptx") return "slides";
  if (ext === ".md" || ext === ".txt") return "notes";
  return "other";
}

/** The title the API would give it: the name without its extension. */
export function titleFrom(filename: string): string {
  const name = filename.trim();
  const dot = name.lastIndexOf(".");
  const stem = (dot > 0 ? name.slice(0, dot) : dot === 0 ? "" : name).replace(/_/g, " ").trim();
  return (stem || "Untitled").slice(0, 200);
}

/** Why the file can't be uploaded, or null if it can. */
export function checkFile(file: { name: string; size: number }): string | null {
  const ext = extension(file.name);
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    const what = ext ? `${ext} files` : "files without an extension";
    return `${file.name}: ${what} can't be uploaded. Use PDF, PPTX, DOCX, MD, TXT, PNG or JPG.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${file.name} is ${formatSize(file.size)}; files can be at most 50 MB.`;
  }
  return null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
