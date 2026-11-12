import { aTopic, roots } from "./fixtures";
import { moveTarget } from "./treeMoves";

// Patterns
//   Creational
//   Structural
// Queues
const tree = roots(
  aTopic("p", "Patterns", [aTopic("c", "Creational"), aTopic("s", "Structural")]),
  aTopic("q", "Queues"),
);
const patterns = tree[0]!;
const children = patterns.children;

test("up and down swap with the neighbouring sibling", () => {
  expect(moveTarget("up", tree, 1, null)).toEqual({ parent_id: null, position: 0 });
  expect(moveTarget("down", tree, 0, null)).toEqual({ parent_id: null, position: 1 });
  expect(moveTarget("down", children, 0, patterns)).toEqual({ parent_id: "p", position: 1 });
});

test("up is unavailable for the first sibling, down for the last", () => {
  expect(moveTarget("up", tree, 0, null)).toBeNull();
  expect(moveTarget("down", tree, 1, null)).toBeNull();
});

test("indent appends to the sibling above", () => {
  expect(moveTarget("indent", tree, 1, null)).toEqual({ parent_id: "p", position: 2 });
  expect(moveTarget("indent", children, 1, patterns)).toEqual({ parent_id: "c", position: 0 });
  expect(moveTarget("indent", tree, 0, null)).toBeNull();
});

test("outdent places the topic right after its parent", () => {
  expect(moveTarget("outdent", children, 1, patterns)).toEqual({ parent_id: null, position: 1 });
  expect(moveTarget("outdent", tree, 0, null)).toBeNull();
});
