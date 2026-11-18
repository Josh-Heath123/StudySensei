import type { SearchResult } from "./api";
import { groupByPage, plainSnippet } from "./searchResults";

const parts = (...runs: [string, boolean][]) =>
  runs.map(([text, highlight]) => ({ text, highlight }));

describe("plainSnippet", () => {
  test("drops bold, italic and inline-code markers but keeps the words", () => {
    expect(plainSnippet(parts(["**Inference** is _slow_ and `fast`", false]))).toEqual(
      parts(["Inference is slow and fast", false]),
    );
  });

  test("keeps the highlight on the words when markers sit in other parts", () => {
    expect(
      plainSnippet(
        parts(
          ["See **", false],
          ["Inference", true],
          ["** and *", false],
          ["rules", true],
          ["*", false],
        ),
      ),
    ).toEqual(parts(["See ", false], ["Inference", true], [" and ", false], ["rules", true]));
  });

  test("strips a marker that is inside a highlighted part", () => {
    expect(plainSnippet(parts(["**Inference**", true], [" rules", false]))).toEqual(
      parts(["Inference", true], [" rules", false]),
    );
  });

  test("drops heading hashes, bullets, numbers and quote marks at line starts", () => {
    expect(
      plainSnippet(parts(["# Week 3\n- layered style\n2. pipes\n> quoted\n  * nested", false])),
    ).toEqual(parts(["Week 3\nlayered style\npipes\nquoted\nnested", false]));
  });

  test("keeps a link's text and an image's alt, not their URLs", () => {
    expect(
      plainSnippet(parts(["Read [the RFC](https://x.org/rfc) and ![a diagram](d.png).", false])),
    ).toEqual(parts(["Read the RFC and a diagram.", false]));
  });

  test("a highlighted link text stays highlighted", () => {
    expect(
      plainSnippet(parts(["Read [", false], ["TCP", true], ["](https://x.org) now", false])),
    ).toEqual(parts(["Read ", false], ["TCP", true], [" now", false]));
  });

  test("drops a bold marker left open where the snippet was cut", () => {
    expect(plainSnippet(parts(["**Inference", true], [" is the", false]))).toEqual(
      parts(["Inference", true], [" is the", false]),
    );
  });

  test("leaves plain text, snake_case and maths alone", () => {
    const plain = parts(["a_b_c costs 2 * 3 * 4", false], ["salted", true]);
    expect(plainSnippet(plain)).toEqual(plain);
  });

  test("a part that was only markup disappears", () => {
    expect(plainSnippet(parts(["**", false], ["TCP", true], ["**", false]))).toEqual(
      parts(["TCP", true]),
    );
  });
});

const hit = (chunk_id: string, material_id: string, page_number: number) =>
  ({ chunk_id, material_id, page_number }) as SearchResult;

describe("groupByPage", () => {
  test("one entry per material page, led by its first (best) hit, in API order", () => {
    const results = [
      hit("a", "m1", 2),
      hit("b", "m2", 2),
      hit("c", "m1", 2),
      hit("d", "m1", 5),
      hit("e", "m1", 2),
    ];
    expect(groupByPage(results)).toEqual([
      { best: results[0], matches: 3 },
      { best: results[1], matches: 1 },
      { best: results[3], matches: 1 },
    ]);
  });

  test("no results, no groups", () => {
    expect(groupByPage([])).toEqual([]);
  });
});
