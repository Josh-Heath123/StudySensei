import { vi } from "vitest";

import {
  APPEARANCE_KEY,
  applyAppearance,
  readAppearance,
  resolveTheme,
  writeAppearance,
} from "./appearance";

afterEach(() => {
  delete document.documentElement.dataset.theme;
  vi.restoreAllMocks();
});

test("System is the default, and only valid choices are read back", () => {
  expect(readAppearance()).toBe("system");
  localStorage.setItem(APPEARANCE_KEY, "sepia");
  expect(readAppearance()).toBe("system");
  writeAppearance("dark");
  expect(readAppearance()).toBe("dark");
  writeAppearance("system");
  expect(localStorage.getItem(APPEARANCE_KEY)).toBeNull();
});

test("System follows the operating system; Light and Dark don't", () => {
  expect(resolveTheme("system", true)).toBe("dark");
  expect(resolveTheme("system", false)).toBe("light");
  expect(resolveTheme("light", true)).toBe("light");
  expect(resolveTheme("dark", false)).toBe("dark");
});

test("applying a choice sets data-theme on <html>", () => {
  applyAppearance("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  applyAppearance("light");
  expect(document.documentElement.dataset.theme).toBe("light");
});

test("storage that throws doesn't break reading or writing", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(readAppearance()).toBe("system");
  expect(() => writeAppearance("dark")).not.toThrow();
});
