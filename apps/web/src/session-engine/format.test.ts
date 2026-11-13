import { formatDuration } from "./format";

const MIN = 60_000;

describe("formatDuration", () => {
  it.each([
    [0, "under a minute"],
    [59_999, "under a minute"],
    [MIN, "1 min"],
    [45 * MIN + 59_000, "45 min"],
    [60 * MIN, "1 h"],
    [192 * MIN, "3 h 12 min"],
    [26 * 60 * MIN + 5 * MIN, "26 h 5 min"],
  ])("%d ms → %s", (ms, text) => {
    expect(formatDuration(ms)).toBe(text);
  });
});
