import { aTopic, roots } from "../modules/fixtures";

import { findTopicName, flattenTopics } from "./topics";

const tree = roots(
  aTopic("t1", "Architecture styles", [aTopic("t2", "Layers"), aTopic("t3", "Pipes and filters")]),
  aTopic("t4", "Quality attributes"),
);

test("flattens the tree in reading order with depths", () => {
  expect(flattenTopics(tree)).toEqual([
    { id: "t1", name: "Architecture styles", depth: 0 },
    { id: "t2", name: "Layers", depth: 1 },
    { id: "t3", name: "Pipes and filters", depth: 1 },
    { id: "t4", name: "Quality attributes", depth: 0 },
  ]);
});

test("finds a topic's name anywhere in the tree", () => {
  expect(findTopicName(tree, "t3")).toBe("Pipes and filters");
  expect(findTopicName(tree, "missing")).toBeNull();
  expect(findTopicName(tree, null)).toBeNull();
});
