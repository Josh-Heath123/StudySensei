import type { TopicMastery } from "./api";

type Band = TopicMastery["band"];

/** The chip's words. The basis sentence beside it says it's an estimate (never an exam prediction). */
export const BAND_LABELS: Record<Band, string> = {
  weak: "Weak",
  developing: "Developing",
  strong: "Strong",
};

export const BAND_VARIANTS: Record<Band, "warning" | "default" | "success"> = {
  weak: "warning",
  developing: "default",
  strong: "success",
};
