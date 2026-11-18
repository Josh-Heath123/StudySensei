/**
 * The appearance setting: System (the default), Light or Dark. It's stored in localStorage
 * and applied as `data-theme` on <html>. index.html runs the same logic inline before the
 * first paint (keep the key and rules in step), so the page never flashes the wrong theme.
 */

export type Appearance = "system" | "light" | "dark";
export type Theme = "light" | "dark";

export const APPEARANCE_KEY = "studysensei.appearance";
export const APPEARANCES: readonly Appearance[] = ["system", "light", "dark"];
const DARK_QUERY = "(prefers-color-scheme: dark)";

function isAppearance(value: unknown): value is Appearance {
  return typeof value === "string" && (APPEARANCES as readonly string[]).includes(value);
}

/** The stored choice; "system" when nothing (or nothing valid) is stored, or storage fails. */
export function readAppearance(): Appearance {
  try {
    const stored = localStorage.getItem(APPEARANCE_KEY);
    return isAppearance(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

/** Store the choice. Storage can be unavailable (private windows); the choice still applies. */
export function writeAppearance(value: Appearance): void {
  try {
    if (value === "system") localStorage.removeItem(APPEARANCE_KEY);
    else localStorage.setItem(APPEARANCE_KEY, value);
  } catch {
    // Not persisted; applied for this page only.
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** The theme a choice resolves to. */
export function resolveTheme(value: Appearance, prefersDark = systemPrefersDark()): Theme {
  if (value === "system") return prefersDark ? "dark" : "light";
  return value;
}

/** Set `data-theme` on <html> for this choice. */
export function applyAppearance(value: Appearance): Theme {
  const theme = resolveTheme(value);
  document.documentElement.dataset.theme = theme;
  return theme;
}

/** While the choice is "system", follow the operating system's changes. Returns an unsubscribe. */
export function followSystemTheme(): () => void {
  if (typeof window.matchMedia !== "function") return () => undefined;
  const query = window.matchMedia(DARK_QUERY);
  const onChange = () => {
    if (readAppearance() === "system") applyAppearance("system");
  };
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
