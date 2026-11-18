/**
 * WCAG contrast for every token pair used for text or controls, in both themes, read from
 * the real stylesheet (docs/DESIGN.md "Contrast"). Text needs 4.5:1; UI boundaries and the
 * focus ring need 3:1. Glass is checked against the worst case that can sit behind it.
 */
/// <reference types="node" />
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { MODULE_SWATCHES } from "@/features/modules/colours";

import { contrastRatio } from "./contrast";

// The stylesheet as written (not as Vite transforms it), read from disk.
// Tests run from apps/web (npm run test -w apps/web), or from the repo root.
const STYLESHEET = ["src/index.css", "apps/web/src/index.css"]
  .map((file) => path.resolve(process.cwd(), file))
  .find((file) => existsSync(file));
if (!STYLESHEET) throw new Error("Can't find apps/web/src/index.css");
const css = readFileSync(STYLESHEET, "utf8");

type Tokens = Record<string, string>;

function block(selector: RegExp): Tokens {
  const match = selector.exec(css);
  if (!match) throw new Error(`No block for ${selector}`);
  const start = match.index + match[0].length;
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]),
  );
}

const light = block(/:root,\s*:root\[data-theme="light"\]\s*\{/);
const dark = block(/:root\[data-theme="dark"\]\s*\{/);

type Rgba = [number, number, number, number];

function parse(colour: string): Rgba {
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(colour);
  if (hex) return [parseInt(hex[1]!, 16), parseInt(hex[2]!, 16), parseInt(hex[3]!, 16), 1];
  const rgba = /^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/.exec(colour);
  if (rgba) return [Number(rgba[1]), Number(rgba[2]), Number(rgba[3]), Number(rgba[4])];
  throw new Error(`Can't read colour ${colour}`);
}

/** `top` (possibly translucent) composited over an opaque `bottom`, as "#RRGGBB". */
function over(top: string, bottom: string): string {
  const [r, g, b, a] = parse(top);
  const [r2, g2, b2] = parse(bottom);
  const mix = [r * a + r2 * (1 - a), g * a + g2 * (1 - a), b * a + b2 * (1 - a)];
  return "#" + mix.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("");
}

const GRADIENT_STOPS = ["#FE6BD4", "#A77BF6", "#5840FF"];
// Anything opaque that can sit behind floating glass: the darkest and lightest surfaces,
// the violet fill, the pink accent and every module colour.
function backdrops(theme: Tokens): string[] {
  return [
    theme.canvas!,
    theme.surface!,
    theme.fg!,
    theme.primary!,
    theme.pink!,
    "#FFFFFF",
    ...MODULE_SWATCHES.map((s) => s.value),
  ];
}

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme", (_name, t) => {
  const backgrounds = { canvas: t.canvas!, surface: t.surface!, "surface-2": t["surface-2"]! };

  it.each(["fg", "muted", "link", "danger", "warning", "success"])(
    "%s text reaches 4.5:1 on canvas and both surfaces",
    (token) => {
      for (const [name, background] of Object.entries(backgrounds)) {
        expect(contrastRatio(t[token]!, background), `${token} on ${name}`).toBeGreaterThanOrEqual(
          4.5,
        );
      }
    },
  );

  it("text on the violet button reaches 4.5:1, at rest and on hover", () => {
    expect(contrastRatio(t["on-primary"]!, t.primary!)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(t["on-primary"]!, t["primary-hover"]!)).toBeGreaterThanOrEqual(4.5);
  });

  it("fg text reaches 4.5:1 on the soft violet accent and on pink", () => {
    expect(contrastRatio(t.fg!, t["accent-soft"]!)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(t.muted!, t["accent-soft"]!)).toBeGreaterThanOrEqual(4.5);
    // Pink is a fill with dark text on it, in both themes.
    expect(contrastRatio(light.fg!, t.pink!)).toBeGreaterThanOrEqual(4.5);
  });

  it("control boundaries and the focus ring reach 3:1", () => {
    for (const background of Object.values(backgrounds)) {
      expect(contrastRatio(t["line-strong"]!, background)).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(t.ring!, background)).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(t["primary-edge"]!, background)).toBeGreaterThanOrEqual(3);
    }
  });

  it.each(["glass-strong", "glass-nav"])(
    "%s keeps fg and muted text at 4.5:1 over anything behind it",
    (token) => {
      for (const behind of backdrops(t)) {
        const glass = over(t[token]!, behind);
        expect(contrastRatio(t.fg!, glass), `fg over ${behind}`).toBeGreaterThanOrEqual(4.5);
        expect(contrastRatio(t.muted!, glass), `muted over ${behind}`).toBeGreaterThanOrEqual(4.5);
      }
    },
  );

  it("the hero's glass keeps its text at 4.5:1 over every point of the gradient", () => {
    for (const stop of GRADIENT_STOPS) {
      const glass = over(t["glass-hero"]!, stop);
      expect(contrastRatio(t.fg!, glass)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(t.muted!, glass)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("the session bar's glass keeps its text at 4.5:1 over the mist", () => {
    for (const mist of [t["mist-a"]!, t["mist-b"]!]) {
      const glass = over(t.glass!, over(mist, t.canvas!));
      expect(contrastRatio(t.fg!, glass)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(t.muted!, glass)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("module colours", () => {
  it.each(MODULE_SWATCHES.map((s) => [s.name, s.value]))(
    "%s %s keeps dark text at 4.5:1 in both themes",
    (_name, value) => {
      expect(contrastRatio(light.fg!, value)).toBeGreaterThanOrEqual(4.5);
    },
  );
});
