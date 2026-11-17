import { describeTopicMap } from "./topicMap";
import { aTopicMap } from "./fixtures";

const NOW = new Date("2026-11-17T10:00:00Z");

test("no AI key comes first and can't build", () => {
  const view = describeTopicMap(aTopicMap({ pending: 2 }), false, NOW);

  expect(view.message).toMatch(/AI isn't set up/);
  expect(view.canBuild).toBe(false);
});

test("nothing eligible says what to upload", () => {
  const view = describeTopicMap(aTopicMap({ eligible: 0 }), true, NOW);

  expect(view.message).toMatch(/Nothing to analyse yet/);
  expect(view.canBuild).toBe(false);
});

test("analysing shows progress and can't be started twice", () => {
  const view = describeTopicMap(aTopicMap({ eligible: 21, analysed: 14, pending: 7 }), true, NOW);

  expect(view.message).toBe("Analysed 14 of 21 materials…");
  expect(view.progress).toEqual({ done: 14, total: 21 });
  expect(view.canBuild).toBe(false);
  expect(view.busy).toBe(true);
});

test("a rate-limited wait says when the AI is back", () => {
  const view = describeTopicMap(
    aTopicMap({ analysed: 1, pending: 1, waiting_until: "2026-11-17T13:30:00Z" }),
    true,
    NOW,
  );

  expect(view.message).toMatch(
    /^The AI is resting until .+ \(free-tier limits\)\. Analysed 1 of 2/,
  );
  expect(view.busy).toBe(true);
});

test("a wait in the past is ignored", () => {
  const view = describeTopicMap(
    aTopicMap({ pending: 1, waiting_until: "2026-11-17T09:00:00Z" }),
    true,
    NOW,
  );

  expect(view.message).toBe("Analysed 0 of 2 materials…");
});

test("merging, then idle with failures explained", () => {
  expect(describeTopicMap(aTopicMap({ analysed: 2, merging: true }), true, NOW).message).toBe(
    "Building the topic map from 2 analysed materials…",
  );

  const idle = describeTopicMap(
    aTopicMap({ analysed: 1, failed: 1, last_error: "Bad shape." }),
    true,
    NOW,
  );
  expect(idle.message).toBe("1 material not analysed yet (1 of 2 done).");
  expect(idle.detail).toBe("1 material couldn't be analysed: Bad shape.");
  expect(idle.canBuild).toBe(true);
});

test("everything analysed can still be built again", () => {
  const view = describeTopicMap(aTopicMap({ analysed: 2 }), undefined, NOW);

  expect(view.message).toBe("All 2 materials analysed. Building again adds only new topics.");
  expect(view.canBuild).toBe(true);
});
