// Module colours from docs/DESIGN.md. Always used as fills behind dark text, so every
// one must reach 4.5:1 against on-fill (INK, checked in lib/contrast.test.ts).
export const MODULE_SWATCHES = [
  { name: "Orange", value: "#FF7A3D" },
  { name: "Yellow", value: "#FFD23F" },
  { name: "Mint", value: "#5EE0B0" },
  { name: "Blue", value: "#8FB8FF" },
  { name: "Lilac", value: "#C9A7FF" },
  { name: "Pink", value: "#FF8FA3" },
  { name: "Lime", value: "#B8E05E" },
  { name: "Cyan", value: "#6ED3E8" },
] as const;

export const DEFAULT_MODULE_COLOUR = MODULE_SWATCHES[0].value;
