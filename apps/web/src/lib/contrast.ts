/** WCAG 2 contrast checks for the colours in docs/DESIGN.md. */

export const INK = "#111111";
export const PAPER = "#FFFFFF";
/** WCAG AA for normal text. */
export const MIN_CONTRAST = 4.5;

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** Relative luminance of a "#RRGGBB" colour (0 = black, 1 = white). */
export function luminance(hex: string): number {
  const match = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`Not a #RRGGBB colour: ${hex}`);
  const [r, g, b] = match.slice(1).map((part) => channel(parseInt(part, 16))) as [
    number,
    number,
    number,
  ];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Contrast ratio between two colours, from 1 (none) to 21 (black on white). */
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/** Module colours are fills behind ink text, so they must reach 4.5:1 against ink. */
export function readableOnInk(hex: string): boolean {
  return contrastRatio(hex, INK) >= MIN_CONTRAST;
}

/** "3.1:1" (rounded down, so a colour is never shown as passing when it doesn't). */
export function formatRatio(ratio: number): string {
  return `${Math.floor(ratio * 10) / 10}:1`;
}
