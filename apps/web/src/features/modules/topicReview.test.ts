import { aTopic, roots } from "./fixtures";
import {
  aiDescendants,
  mergeTargets,
  reviewLine,
  reviewProgress,
  unreviewedOnly,
} from "./topicReview";

const stats = { kept: 40, renamed: 6, merged: 3, dismissed: 2, unreviewed: 2 };

test("the review line and progress count every outcome", () => {
  expect(reviewLine(stats)).toBe("Review: 40 kept, 6 renamed, 3 merged, 2 dismissed");
  expect(reviewProgress(stats)).toEqual({ done: 51, total: 53 });
  expect(reviewLine({ kept: 0, renamed: 0, merged: 0, dismissed: 0, unreviewed: 9 })).toBeNull();
  expect(reviewLine(undefined)).toBeNull();
});

const ai = { source: "ai" as const };
const TREE = roots(
  aTopic("u", "Mine", [aTopic("a1", "AI under mine", [], ai), aTopic("u2", "Also mine")]),
  aTopic("a2", "AI root", [aTopic("u3", "Mine under AI"), aTopic("a3", "AI child", [], ai)], ai),
  aTopic("u4", "Only mine"),
);

test("the review filter keeps AI topics and the ancestors holding them", () => {
  const shown = unreviewedOnly(TREE);

  expect(shown.map((n) => n.id)).toEqual(["u", "a2"]);
  expect(shown[0]!.children.map((n) => n.id)).toEqual(["a1"]);
  expect(shown[1]!.children.map((n) => n.id)).toEqual(["a3"]);
});

test("AI descendants and merge targets", () => {
  expect(aiDescendants(TREE[1]!)).toBe(1);
  expect(mergeTargets(TREE, "a2").map((t) => [t.id, t.depth])).toEqual([
    ["u", 0],
    ["a1", 1],
    ["u2", 1],
    ["u4", 0],
  ]);
});
