import {
  countsLine,
  flattenTopics,
  fromNow,
  generationText,
  keyPointLines,
  memoryText,
  nextDueText,
  shareRight,
  sourceChip,
  suggestFromTicks,
  weakestFirst,
} from "./practiceText";
import { aGeneration } from "./fixtures";

const NOW = new Date("2026-11-23T10:00:00Z");
const later = (minutes: number) => new Date(NOW.getTime() + minutes * 60_000).toISOString();

test("the tick list suggests a grade the way the server marks: all Good, half Hard, else Again", () => {
  expect([3, 2, 1, 0].map((ticked) => suggestFromTicks(ticked, 3))).toEqual([3, 2, 1, 1]);
  expect(suggestFromTicks(1, 2)).toBe(2);
  expect(suggestFromTicks(2, 5)).toBe(1);
  expect(suggestFromTicks(1, 1)).toBe(3);
  expect(suggestFromTicks(0, 0)).toBe(1);
});

test("times from now, rounded and never zero minutes", () => {
  expect(
    [0.2, 1, 10, 59, 61, 180, 60 * 24, 60 * 24 * 4].map((m) => fromNow(later(m), NOW)),
  ).toEqual([
    "now",
    "in 1 min",
    "in 10 min",
    "in 59 min",
    "in 1 h",
    "in 3 h",
    "in 1 day",
    "in 4 days",
  ]);
  expect(fromNow(later(-30), NOW)).toBe("now");
});

test("the next review: under a minute away or past says so, never a bare now", () => {
  expect(nextDueText(later(0.3), NOW)).toBe("in under a minute");
  expect(nextDueText(later(59 / 60), NOW)).toBe("in under a minute");
  expect(nextDueText(later(-5), NOW)).toBe("in under a minute");
  expect(nextDueText(later(1), NOW)).toBe("in 1 min");
  expect(nextDueText(later(180), NOW)).toBe("in 3 h");
});

test("the counts line leaves out a zero", () => {
  expect(countsLine({ due_now: 4, new_today_left: 12 })).toBe("4 due now · 12 new today");
  expect(countsLine({ due_now: 0, new_today_left: 3 })).toBe("3 new today");
  expect(countsLine({ due_now: 0, new_today_left: 0 })).toBe("");
});

test("an item's memory: its state and when it's due", () => {
  const memory = {
    state: "learning" as const,
    due: later(10),
    stability: 0.2,
    difficulty: 6,
    retrievability: null,
    reps: 1,
    lapses: 0,
  };
  expect(memoryText(memory, NOW)).toBe("Learning · due in 10 min");
  expect(memoryText({ ...memory, state: "review", due: later(-5) }, NOW)).toBe("Review · due now");
  expect(memoryText({ ...memory, state: "new", due: null }, NOW)).toBe("New");
});

test("a source chip is the material's code and the page", () => {
  expect(sourceChip("CH05 Network Security", 14)).toBe("CH05 p14");
  expect(sourceChip("Week 6 slides", 3)).toBe("Week 6 p3");
  expect(sourceChip("Lecture notes on hashing", 7)).toBe("Lecture notes o… p7");
  expect(sourceChip("Notes", 1)).toBe("Notes p1");
});

test("topics weakest first, ties by name", () => {
  const found = weakestFirst([
    { name: "B", value: 0.7 },
    { name: "C", value: 0.2 },
    { name: "A", value: 0.7 },
  ]);
  expect(found.map((t) => t.name)).toEqual(["C", "A", "B"]);
});

test("a generation's state in words", () => {
  expect(generationText(undefined)).toBeNull();
  expect(generationText(aGeneration({ status: "queued" }))).toBe("Queued…");
  expect(generationText(aGeneration({ status: "running" }))).toBe("Writing practice…");
  expect(generationText(aGeneration({ status: "succeeded", produced: 8 }))).toBe("8 written");
  expect(generationText(aGeneration({ status: "failed", error: "The AI is busy." }))).toBe(
    "The AI is busy.",
  );
});

test("the share right counts Good and Easy", () => {
  expect(shareRight([1, 2, 3, 4])).toBe(50);
  expect(shareRight([])).toBe(0);
});

test("a topic tree flattens in course order with depths", () => {
  const leaf = { id: "c", name: "Chaining", children: [] };
  const tree = [
    { id: "a", name: "Hashing", children: [{ id: "b", name: "Collisions", children: [leaf] }] },
    { id: "d", name: "Sorting", children: [] },
  ];
  expect(flattenTopics(tree).map((t) => `${t.depth}:${t.name}`)).toEqual([
    "0:Hashing",
    "1:Collisions",
    "2:Chaining",
    "0:Sorting",
  ]);
});

test("key points are typed one per line", () => {
  expect(keyPointLines(" Spreads keys \n\n Short buckets\n")).toEqual([
    "Spreads keys",
    "Short buckets",
  ]);
});
