import { MODULE_SWATCHES } from "@/features/modules/colours";

import { contrastRatio, formatRatio, INK, MIN_CONTRAST, PAPER, readableOnInk } from "./contrast";

describe("contrastRatio", () => {
  it("gives the WCAG extremes", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#777777")).toBe(1);
  });

  it("doesn't care about order or case", () => {
    expect(contrastRatio(INK, PAPER)).toBe(contrastRatio("#ffffff", "#0b0b12"));
  });

  it("rejects anything that isn't #RRGGBB", () => {
    expect(() => contrastRatio("blue", INK)).toThrow();
  });
});

describe("module swatches (docs/DESIGN.md)", () => {
  it.each(MODULE_SWATCHES.map((s) => [s.name, s.value]))(
    "%s %s reaches 4.5:1 behind dark text",
    (_name, value) => {
      expect(contrastRatio(value, INK)).toBeGreaterThanOrEqual(MIN_CONTRAST);
      expect(readableOnInk(value)).toBe(true);
    },
  );

  it("rejects dark colours, such as the old indigo preset", () => {
    for (const dark of ["#5856D6", "#1D1D1F", "#C4161C"]) {
      expect(readableOnInk(dark)).toBe(false);
    }
  });
});

// Token contrast, in both themes, is checked against the stylesheet in tokens.test.ts.

describe("formatRatio", () => {
  it("rounds down so a failing colour never looks like it passes", () => {
    expect(formatRatio(4.49)).toBe("4.4:1");
    expect(formatRatio(7)).toBe("7:1");
  });
});
