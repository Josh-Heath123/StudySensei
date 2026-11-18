import {
  aggregate,
  analyseFrame,
  phaseAt,
  PROTOCOL,
  PROTOCOL_SECONDS,
  schedule,
  stateAt,
  summarise,
  type Phase,
} from "./metrics";

const T0 = 1_700_000_000_000;

describe("phase marking", () => {
  test("the protocol is 3 minutes: 30 s visible, 60 s other tab, 60 s minimised, 30 s visible", () => {
    expect(PROTOCOL.map((phase) => [phase.name, phase.seconds])).toEqual([
      ["visible", 30],
      ["other tab", 60],
      ["minimised", 60],
      ["visible again", 30],
    ]);
    expect(PROTOCOL_SECONDS).toBe(180);
  });

  test("phaseAt gives the phase, its index and the time left, at the boundaries too", () => {
    expect(phaseAt(-1)).toBeNull();
    expect(phaseAt(0)).toMatchObject({ index: 0, remainingMs: 30_000 });
    expect(phaseAt(29_999)?.phase.name).toBe("visible");
    expect(phaseAt(30_000)).toMatchObject({ index: 1, remainingMs: 60_000 });
    expect(phaseAt(150_000)?.phase.name).toBe("visible again");
    expect(phaseAt(179_999)?.remainingMs).toBe(1);
    expect(phaseAt(180_000)).toBeNull();
  });

  test("schedule gives each phase's wall-clock start and end", () => {
    expect(
      schedule(T0).map((entry) => [entry.name, entry.startsAt - T0, entry.endsAt - T0]),
    ).toEqual([
      ["visible", 0, 30_000],
      ["other tab", 30_000, 90_000],
      ["minimised", 90_000, 150_000],
      ["visible again", 150_000, 180_000],
    ]);
  });
});

describe("sample aggregation", () => {
  const short: Phase[] = [
    { name: "visible", seconds: 2, instruction: "" },
    { name: "other tab", seconds: 2, instruction: "" },
  ];

  test("counts frames per second and the gaps between them, marking the phase", () => {
    // Second 0: 10 frames 100 ms apart. Second 1: 2 frames. Second 2: none. Second 3: 1 frame.
    const frames = [
      ...Array.from({ length: 10 }, (_, i) => T0 + i * 100),
      T0 + 1_200,
      T0 + 1_700,
      T0 + 3_500,
    ];

    const samples = aggregate({
      startMs: T0,
      endMs: T0 + 4_000,
      frames,
      visibility: [],
      pip: [],
      protocol: short,
    });

    expect(samples.map((s) => [s.second, s.phase, s.frames])).toEqual([
      [0, "visible", 10],
      [1, "visible", 2],
      [2, "other tab", 0],
      [3, "other tab", 1],
    ]);
    expect(samples[0]).toMatchObject({ meanGapMs: 100, maxGapMs: 100 });
    // 900 → 1200 and 1200 → 1700.
    expect(samples[1]).toMatchObject({ meanGapMs: 400, maxGapMs: 500 });
    expect(samples[2]).toMatchObject({ meanGapMs: null, maxGapMs: null });
    // The long gap is counted in the second where the next frame arrived.
    expect(samples[3]).toMatchObject({ meanGapMs: 1_800, maxGapMs: 1_800 });
  });

  test("a frame before the start only seeds the first gap", () => {
    const samples = aggregate({
      startMs: T0,
      endMs: T0 + 1_000,
      frames: [T0 - 50, T0 + 150],
      visibility: [],
      pip: [],
    });

    expect(samples[0]).toMatchObject({ frames: 1, meanGapMs: 200 });
  });

  test("visibility and PiP are the state in force at the end of each second", () => {
    const samples = aggregate({
      startMs: T0,
      endMs: T0 + 3_000,
      frames: [],
      visibility: [
        { at: T0 + 400, value: "hidden" },
        { at: T0 + 2_100, value: "visible" },
      ],
      pip: [{ at: T0 + 1_999, value: true }],
    });

    expect(samples.map((s) => [s.visibility, s.pipOpen])).toEqual([
      ["hidden", false],
      ["hidden", true],
      ["visible", true],
    ]);
    expect(stateAt([{ at: 5, value: "b" }], 4, "a")).toBe("a");
  });

  test("a partial last second is still a sample", () => {
    const samples = aggregate({
      startMs: T0,
      endMs: T0 + 2_500,
      frames: [T0 + 2_400],
      visibility: [],
      pip: [],
    });

    expect(samples).toHaveLength(3);
    expect(samples[2]?.frames).toBe(1);
  });

  test("summarise reports each phase's mean and minimum rate and seconds at target", () => {
    const frames = [
      ...Array.from({ length: 12 }, (_, i) => T0 + i * 80), // second 0: 12 frames
      ...Array.from({ length: 6 }, (_, i) => T0 + 1_000 + i * 150), // second 1: 6
      T0 + 2_500, // second 2: 1
      T0 + 3_100, // second 3: 1
    ];
    const samples = aggregate({
      startMs: T0,
      endMs: T0 + 4_000,
      frames,
      visibility: [],
      pip: [],
      protocol: short,
    });

    expect(summarise(samples)).toEqual([
      { phase: "visible", seconds: 2, meanFps: 9, minFps: 6, secondsAtTarget: 2, maxGapMs: 150 },
      { phase: "other tab", seconds: 2, meanFps: 1, minFps: 1, secondsAtTarget: 0, maxGapMs: 750 },
    ]);
  });
});

describe("the frame workload", () => {
  test("mean brightness and the difference from the previous frame", () => {
    const grey = (value: number, pixels: number) =>
      new Uint8ClampedArray(
        Array.from({ length: pixels }, () => [value, value, value, 255]).flat(),
      );
    const first = new Float32Array(4);
    const second = new Float32Array(4);

    const a = analyseFrame(grey(100, 4), null, first);
    const b = analyseFrame(grey(110, 4), first, second);

    expect(a.brightness).toBeCloseTo(100);
    expect(a.difference).toBe(0);
    expect(b.brightness).toBeCloseTo(110);
    expect(b.difference).toBeCloseTo(10);
  });
});
