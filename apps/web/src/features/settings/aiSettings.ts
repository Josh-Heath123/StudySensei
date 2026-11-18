/** Words and formats for the AI providers section. */

export const PROVIDER_NAMES: Record<string, string> = {
  gemini: "Gemini",
  groq: "Groq",
  ollama: "Ollama",
};

/** What each role is used for, in plain words. */
export const ROLE_USES: Record<string, string> = {
  smart: "The tutor",
  bulk: "Tagging",
  vision: "Images",
  long: "Whole documents and topic maps",
};

export const ROLE_ORDER = ["smart", "bulk", "vision", "long"];

const resetFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** A reset time in the browser's own time zone: "Thu 09:00". */
export function formatReset(iso: string): string {
  return resetFormat.format(new Date(iso));
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}
