import { useSyncExternalStore } from "react";

/**
 * Whether a CSS media query matches now, kept up to date. Without `matchMedia` (jsdom in
 * tests, unless a test stubs it) it's `fallback`.
 */
export function useMediaQuery(query: string, fallback = false): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window.matchMedia !== "function") return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : fallback),
    () => fallback,
  );
}

/** docs/DESIGN.md "Layout and responsive": the tutor is a side panel from 1024 px. */
export const DESKTOP = "(min-width: 1024px)";
