/**
 * Pure parts of the S1 spike: the per-frame workload, the protocol's phases, and turning
 * frame timestamps into per-second samples. Everything is a function of its inputs, so the
 * results don't depend on when the page's own timers happened to run (they're throttled in
 * a background tab; the frame timestamps aren't).
 */

// --- the per-frame workload (a stand-in for face detection) ---

/** Frames are scaled to this size before the workload runs, in every mode. */
export const WORK_WIDTH = 160;
export const WORK_HEIGHT = 120;

export type FrameStats = { brightness: number; difference: number };

/**
 * Mean brightness (0–255, Rec. 601 luma) and the mean absolute luma difference from the
 * previous frame (0 for the first). `luma` receives this frame's luma for the next call.
 */
export function analyseFrame(
  rgba: Uint8ClampedArray,
  previousLuma: Float32Array | null,
  luma: Float32Array,
): FrameStats {
  const pixels = rgba.length / 4;
  let sum = 0;
  let difference = 0;
  for (let i = 0; i < pixels; i += 1) {
    const y = 0.299 * rgba[i * 4]! + 0.587 * rgba[i * 4 + 1]! + 0.114 * rgba[i * 4 + 2]!;
    luma[i] = y;
    sum += y;
    if (previousLuma) difference += Math.abs(y - previousLuma[i]!);
  }
  return {
    brightness: pixels ? sum / pixels : 0,
    difference: pixels && previousLuma ? difference / pixels : 0,
  };
}

// --- the protocol ---

export type PhaseName = "visible" | "other tab" | "minimised" | "visible again";

export type Phase = { name: PhaseName; seconds: number; instruction: string };

/** About 3 minutes per mode: 30 s visible, 60 s on another tab, 60 s minimised, 30 s visible. */
export const PROTOCOL: readonly Phase[] = [
  { name: "visible", seconds: 30, instruction: "Keep this tab visible and in front." },
  {
    name: "other tab",
    seconds: 60,
    instruction: "Switch to another tab in this window (Ctrl+Tab), and stay there.",
  },
  {
    name: "minimised",
    seconds: 60,
    instruction: "Come back if you like, then minimise the whole browser window.",
  },
  {
    name: "visible again",
    seconds: 30,
    instruction: "Restore the window and bring this tab back to the front.",
  },
];

export const PROTOCOL_SECONDS = PROTOCOL.reduce((total, phase) => total + phase.seconds, 0);

/** The phase at `elapsedMs` since the run started, or null before the start and after the end. */
export function phaseAt(
  elapsedMs: number,
  protocol: readonly Phase[] = PROTOCOL,
): { phase: Phase; index: number; remainingMs: number } | null {
  if (elapsedMs < 0) return null;
  let start = 0;
  for (const [index, phase] of protocol.entries()) {
    const end = start + phase.seconds * 1000;
    if (elapsedMs < end) return { phase, index, remainingMs: end - elapsedMs };
    start = end;
  }
  return null;
}

/** When each phase starts and ends, as wall-clock times, for the instructions. */
export function schedule(startMs: number, protocol: readonly Phase[] = PROTOCOL) {
  let at = startMs;
  return protocol.map((phase) => {
    const entry = { name: phase.name, startsAt: at, endsAt: at + phase.seconds * 1000 };
    at = entry.endsAt;
    return entry;
  });
}

// --- per-second samples ---

/** A change of state at a time (ms since the epoch), e.g. visibility "hidden". */
export type StateChange<T> = { at: number; value: T };

export type Sample = {
  /** Whole seconds since the run started (this sample covers [second, second + 1)). */
  second: number;
  phase: PhaseName | null;
  /** Frames processed in this second. */
  frames: number;
  /** Time between consecutive frames that ended in this second, in ms (null if fewer than one gap). */
  meanGapMs: number | null;
  maxGapMs: number | null;
  /** document.visibilityState at the end of the second. */
  visibility: DocumentVisibilityState;
  pipOpen: boolean;
};

/** The value in force at time `at`: the last change at or before it, else `initial`. */
export function stateAt<T>(changes: readonly StateChange<T>[], at: number, initial: T): T {
  let value = initial;
  for (const change of changes) {
    if (change.at > at) break;
    value = change.value;
  }
  return value;
}

/**
 * One sample per second from `startMs` up to `endMs` (exclusive), from the times frames were
 * processed (ms since the epoch, ascending) and the visibility and PiP changes (ascending).
 */
export function aggregate(input: {
  startMs: number;
  endMs: number;
  frames: readonly number[];
  visibility: readonly StateChange<DocumentVisibilityState>[];
  pip: readonly StateChange<boolean>[];
  initialVisibility?: DocumentVisibilityState;
  protocol?: readonly Phase[];
}): Sample[] {
  const { startMs, endMs, frames } = input;
  const seconds = Math.max(0, Math.ceil((endMs - startMs) / 1000));
  const samples: Sample[] = [];
  let frameIndex = 0;
  let previous: number | null = null;
  // Frames before the start only seed the first gap.
  while (frameIndex < frames.length && frames[frameIndex]! < startMs) {
    previous = frames[frameIndex]!;
    frameIndex += 1;
  }
  for (let second = 0; second < seconds; second += 1) {
    const from = startMs + second * 1000;
    const to = Math.min(from + 1000, endMs);
    let count = 0;
    let gapSum = 0;
    let gaps = 0;
    let maxGap: number | null = null;
    while (frameIndex < frames.length && frames[frameIndex]! < to) {
      const at = frames[frameIndex]!;
      count += 1;
      if (previous !== null) {
        const gap = at - previous;
        gapSum += gap;
        gaps += 1;
        maxGap = maxGap === null ? gap : Math.max(maxGap, gap);
      }
      previous = at;
      frameIndex += 1;
    }
    const end = to - 1;
    samples.push({
      second,
      phase: phaseAt(from - startMs, input.protocol)?.phase.name ?? null,
      frames: count,
      meanGapMs: gaps ? Math.round(gapSum / gaps) : null,
      maxGapMs: maxGap === null ? null : Math.round(maxGap),
      visibility: stateAt(input.visibility, end, input.initialVisibility ?? "visible"),
      pipOpen: stateAt(input.pip, end, false),
    });
  }
  return samples;
}

export type PhaseSummary = {
  phase: PhaseName;
  seconds: number;
  meanFps: number;
  minFps: number;
  /** Seconds that reached the target rate. */
  secondsAtTarget: number;
  maxGapMs: number | null;
};

/** The ≥ 5 frames a second the spike asks for. */
export const TARGET_FPS = 5;

/** Per phase: mean and minimum frames a second, seconds at the target, and the longest gap. */
export function summarise(samples: readonly Sample[], target = TARGET_FPS): PhaseSummary[] {
  const byPhase = new Map<PhaseName, Sample[]>();
  for (const sample of samples) {
    if (!sample.phase) continue;
    byPhase.set(sample.phase, [...(byPhase.get(sample.phase) ?? []), sample]);
  }
  return [...byPhase.entries()].map(([phase, list]) => {
    const fps = list.map((sample) => sample.frames);
    const gaps = list.map((sample) => sample.maxGapMs).filter((gap): gap is number => gap !== null);
    return {
      phase,
      seconds: list.length,
      meanFps: Math.round((fps.reduce((a, b) => a + b, 0) / list.length) * 10) / 10,
      minFps: Math.min(...fps),
      secondsAtTarget: fps.filter((value) => value >= target).length,
      maxGapMs: gaps.length ? Math.max(...gaps) : null,
    };
  });
}
