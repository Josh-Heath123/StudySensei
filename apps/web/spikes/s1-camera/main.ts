/**
 * Spike S1: can the browser keep processing webcam frames at ≥ 5 a second while the tab is in
 * the background, hidden or minimised, and which technique makes that hold?
 *
 * Camera frames never leave the browser: each is reduced to two numbers (brightness and frame
 * difference) and dropped. Nothing is uploaded or stored; the only output is the JSON file the
 * user chooses to download, which holds timings, not images.
 */
import {
  aggregate,
  analyseFrame,
  phaseAt,
  PROTOCOL,
  PROTOCOL_SECONDS,
  schedule,
  summarise,
  TARGET_FPS,
  WORK_HEIGHT,
  WORK_WIDTH,
  type StateChange,
} from "./metrics";
import type { FromWorker, ToWorker } from "./worker";

type ModeId = "rvfc" | "interval" | "worker" | "worker-pip" | "worker-lock";

const MODES: { id: ModeId; label: string; detail: string; supported: () => boolean }[] = [
  {
    id: "rvfc",
    label: "a. Main thread, requestVideoFrameCallback",
    detail: "A <video> element plays the camera; each new frame calls back on the main thread.",
    supported: () => "requestVideoFrameCallback" in HTMLVideoElement.prototype,
  },
  {
    id: "interval",
    label: "b. Main thread, setInterval every 100 ms",
    detail: "A timer grabs the <video>'s current frame ten times a second.",
    supported: () => true,
  },
  {
    id: "worker",
    label: "c. Web Worker fed by MediaStreamTrackProcessor",
    detail:
      "The camera track is transferred to a worker, which reads frames from a MediaStreamTrackProcessor.",
    supported: () => typeof MediaStreamTrackProcessor !== "undefined",
  },
  {
    id: "worker-pip",
    label: "d. Worker + Document Picture-in-Picture",
    detail: "Mode c, plus a small always-on-top window with a preview and the countdown.",
    supported: () =>
      typeof MediaStreamTrackProcessor !== "undefined" &&
      typeof documentPictureInPicture !== "undefined",
  },
  {
    id: "worker-lock",
    label: "e. Worker + a held Web Lock",
    detail:
      "Mode c, plus a Web Lock held for the whole run. Chrome's tab-freezing heuristics skip pages " +
      "holding a Web Lock. A heuristic, not a guarantee: a risk if the result depends on it.",
    supported: () => typeof MediaStreamTrackProcessor !== "undefined" && "locks" in navigator,
  },
];

const epochNow = () => performance.timeOrigin + performance.now();
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const clock = (at: number) => new Date(at).toLocaleTimeString([], { hour12: false });

// --- page state ---

let stream: MediaStream | null = null;
let run: Run | null = null;
let lastResults: Results | null = null;

type Run = {
  mode: ModeId;
  startMs: number;
  frames: number[];
  visibility: StateChange<DocumentVisibilityState>[];
  pip: StateChange<boolean>[];
  initialVisibility: DocumentVisibilityState;
  source: string;
  keepAlive: string | null;
  errors: string[];
  stop: () => void;
  pipWindow: Window | null;
};

type Results = {
  spike: "S1 camera in the browser";
  schema: 1;
  mode: ModeId;
  modeLabel: string;
  frameSource: string;
  keepAlive: string | null;
  browser: string;
  os: string;
  userAgent: string;
  startedAt: string;
  workload: string;
  targetFps: number;
  schedule: { phase: string; startsAt: string; endsAt: string }[];
  summary: ReturnType<typeof summarise>;
  samples: ReturnType<typeof aggregate>;
  errors: string[];
};

// --- browser and OS, for the results file ---

async function browserInfo(): Promise<{ browser: string; os: string }> {
  const data = navigator.userAgentData;
  if (data) {
    try {
      const high = await data.getHighEntropyValues(["fullVersionList", "platformVersion"]);
      const brands = (high.fullVersionList ?? data.brands).filter(
        (item) => !/not.?a.?brand/i.test(item.brand),
      );
      const named = brands.find((item) => item.brand !== "Chromium") ?? brands[0];
      return {
        browser: named ? `${named.brand} ${named.version}` : "unknown",
        os: `${data.platform} ${high.platformVersion ?? ""}`.trim(),
      };
    } catch {
      // Fall through to the user agent string.
    }
  }
  return { browser: navigator.userAgent, os: navigator.platform || "unknown" };
}

// --- the camera, asked for once ---

async function enableCamera(): Promise<void> {
  stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } },
    audio: false,
  });
  const preview = $<HTMLVideoElement>("preview");
  preview.srcObject = stream;
  await preview.play();
  const settings = stream.getVideoTracks()[0]?.getSettings();
  $("camera-status").textContent =
    `Camera on: ${settings?.width}×${settings?.height} at ${settings?.frameRate ?? "?"} frames a second.`;
  $<HTMLButtonElement>("enable").disabled = true;
  $<HTMLButtonElement>("start").disabled = false;
}

// --- the main-thread workload ---

function mainThreadWorkload(video: HTMLVideoElement, record: (at: number) => void) {
  const canvas = document.createElement("canvas");
  canvas.width = WORK_WIDTH;
  canvas.height = WORK_HEIGHT;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  let previous: Float32Array | null = null;
  let current: Float32Array = new Float32Array(WORK_WIDTH * WORK_HEIGHT);
  return (at: number) => {
    if (!context || video.readyState < 2) return;
    context.drawImage(video, 0, 0, WORK_WIDTH, WORK_HEIGHT);
    analyseFrame(context.getImageData(0, 0, WORK_WIDTH, WORK_HEIGHT).data, previous, current);
    [previous, current] = [current, previous ?? new Float32Array(WORK_WIDTH * WORK_HEIGHT)];
    record(at);
  };
}

// --- starting a run ---

async function start(mode: ModeId): Promise<void> {
  if (!stream || run) return;
  const camera = stream.getVideoTracks()[0];
  if (!camera) return;
  // PiP must be requested while the click still counts as a user gesture: before any await.
  const pipRequest =
    mode === "worker-pip" && documentPictureInPicture
      ? documentPictureInPicture.requestWindow({ width: 320, height: 260 })
      : null;

  const current: Run = {
    mode,
    startMs: epochNow(),
    frames: [],
    visibility: [],
    pip: [],
    initialVisibility: document.visibilityState,
    source: "",
    keepAlive: null,
    errors: [],
    stop: () => undefined,
    pipWindow: null,
  };
  const record = (at: number) => current.frames.push(at);
  const stops: (() => void)[] = [];

  if (mode === "rvfc" || mode === "interval") {
    const video = $<HTMLVideoElement>("preview");
    const work = mainThreadWorkload(video, record);
    if (mode === "rvfc") {
      let handle = 0;
      const onFrame: VideoFrameRequestCallback = (now) => {
        work(performance.timeOrigin + now);
        handle = video.requestVideoFrameCallback(onFrame);
      };
      handle = video.requestVideoFrameCallback(onFrame);
      stops.push(() => video.cancelVideoFrameCallback(handle));
      current.source = "main thread, requestVideoFrameCallback on the <video>";
    } else {
      const timer = window.setInterval(() => work(epochNow()), 100);
      stops.push(() => window.clearInterval(timer));
      current.source = "main thread, setInterval(100 ms) on the <video>";
    }
  } else {
    const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<FromWorker>) => {
      const message = event.data;
      if (message.type === "frame") record(message.at);
      else if (message.type === "started") current.source = `worker, ${message.source}`;
      else current.errors.push(message.message);
    };
    // Each run gets its own clone, so the page's preview keeps the original.
    const track = camera.clone();
    try {
      worker.postMessage({ type: "start", track } satisfies ToWorker, [
        track as unknown as Transferable,
      ]);
    } catch {
      // This browser can't transfer a track: make the processor here and transfer its stream.
      const readable = new MediaStreamTrackProcessor({ track }).readable;
      worker.postMessage({ type: "start", readable } satisfies ToWorker, [
        readable as unknown as Transferable,
      ]);
      stops.push(() => track.stop());
    }
    stops.push(() => {
      worker.postMessage({ type: "stop" } satisfies ToWorker);
      window.setTimeout(() => worker.terminate(), 500);
    });

    if (mode === "worker-lock") {
      let release = () => undefined as void;
      const held = new Promise<void>((resolve) => (release = resolve));
      void navigator.locks.request("studysensei-s1-keep-alive", () => held);
      current.keepAlive = "Web Lock held for the whole run (navigator.locks.request)";
      stops.push(() => release());
    }
  }

  if (pipRequest) {
    try {
      const pipWindow = await pipRequest;
      current.pipWindow = pipWindow;
      current.pip.push({ at: epochNow(), value: true });
      pipWindow.document.body.style.cssText =
        "margin:0;font:13px system-ui;background:#111;color:#fff";
      const video = pipWindow.document.createElement("video");
      video.muted = true;
      video.autoplay = true;
      video.playsInline = true;
      video.style.cssText = "width:100%;display:block";
      video.srcObject = stream;
      const status = pipWindow.document.createElement("p");
      status.id = "pip-status";
      status.style.cssText = "margin:6px 8px";
      pipWindow.document.body.append(video, status);
      pipWindow.addEventListener("pagehide", () =>
        current.pip.push({ at: epochNow(), value: false }),
      );
      current.keepAlive = "Document Picture-in-Picture window with a preview";
      stops.push(() => pipWindow.close());
    } catch (error) {
      current.errors.push(
        `Picture-in-Picture: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  current.stop = () => stops.forEach((stop) => stop());
  run = current;
  showSchedule(current.startMs);
  $<HTMLButtonElement>("start").disabled = true;
  $<HTMLButtonElement>("stop").disabled = false;
  $<HTMLButtonElement>("download").disabled = true;
  $<HTMLSelectElement>("mode").disabled = true;
}

async function finish(): Promise<void> {
  const ended = run;
  if (!ended) return;
  run = null;
  ended.stop();
  const endMs = Math.min(epochNow(), ended.startMs + PROTOCOL_SECONDS * 1000);
  const samples = aggregate({
    startMs: ended.startMs,
    endMs,
    frames: ended.frames,
    visibility: ended.visibility,
    pip: ended.pip,
    initialVisibility: ended.initialVisibility,
  });
  const { browser, os } = await browserInfo();
  lastResults = {
    spike: "S1 camera in the browser",
    schema: 1,
    mode: ended.mode,
    modeLabel: MODES.find((mode) => mode.id === ended.mode)?.label ?? ended.mode,
    frameSource: ended.source,
    keepAlive: ended.keepAlive,
    browser,
    os,
    userAgent: navigator.userAgent,
    startedAt: new Date(ended.startMs).toISOString(),
    workload: `scaled to ${WORK_WIDTH}×${WORK_HEIGHT}; mean brightness and mean frame difference`,
    targetFps: TARGET_FPS,
    schedule: schedule(ended.startMs).map((entry) => ({
      phase: entry.name,
      startsAt: new Date(entry.startsAt).toISOString(),
      endsAt: new Date(entry.endsAt).toISOString(),
    })),
    summary: summarise(samples),
    samples,
    errors: ended.errors,
  };
  renderSummary(lastResults);
  $<HTMLButtonElement>("start").disabled = false;
  $<HTMLButtonElement>("stop").disabled = true;
  $<HTMLButtonElement>("download").disabled = false;
  $<HTMLSelectElement>("mode").disabled = false;
}

function download(): void {
  if (!lastResults) return;
  const blob = new Blob([JSON.stringify(lastResults, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  const stamp = lastResults.startedAt.replace(/[:.]/g, "-");
  link.href = URL.createObjectURL(blob);
  link.download = `s1-camera-${lastResults.mode}-${stamp}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// --- the live readout (its timer is throttled in the background; the data isn't) ---

function showSchedule(startMs: number): void {
  const list = $("schedule");
  list.replaceChildren(
    ...schedule(startMs).map((entry, index) => {
      const item = document.createElement("li");
      item.textContent = `${clock(entry.startsAt)}–${clock(entry.endsAt)}: ${PROTOCOL[index]?.instruction ?? ""}`;
      return item;
    }),
  );
}

function tick(): void {
  if (!run) return;
  const now = epochNow();
  const elapsed = now - run.startMs;
  const at = phaseAt(elapsed);
  if (!at) {
    void finish();
    return;
  }
  const countdown = `${at.phase.name}: ${Math.ceil(at.remainingMs / 1000)} s left (phase ${at.index + 1} of ${PROTOCOL.length})`;
  $("phase").textContent = countdown;
  $("instruction").textContent = at.phase.instruction;
  const pipStatus = run.pipWindow?.document.getElementById("pip-status");
  if (pipStatus) pipStatus.textContent = `${countdown}. ${at.phase.instruction}`;

  const samples = aggregate({
    startMs: run.startMs,
    endMs: run.startMs + Math.floor(elapsed / 1000) * 1000,
    frames: run.frames,
    visibility: run.visibility,
    pip: run.pip,
    initialVisibility: run.initialVisibility,
  });
  const last = samples.at(-1);
  $("readout").textContent = last
    ? `${last.frames} frames/s · gap ${last.meanGapMs ?? "–"} ms (max ${last.maxGapMs ?? "–"}) · ` +
      `${last.visibility} · PiP ${last.pipOpen ? "open" : "closed"} · source: ${run.source || "starting…"}`
    : "Waiting for the first second…";
  const log = $("log");
  log.textContent = samples
    .slice(-12)
    .map(
      (sample) =>
        `${String(sample.second).padStart(3)} s  ${String(sample.frames).padStart(3)} fps  ` +
        `gap ${String(sample.meanGapMs ?? "–").padStart(5)} ms  ${sample.visibility.padEnd(7)}  ` +
        `PiP ${sample.pipOpen ? "open  " : "closed"}  ${sample.phase ?? ""}`,
    )
    .join("\n");
}

function renderSummary(results: Results): void {
  $("summary").textContent = [
    `${results.modeLabel} (${results.frameSource || "no frames"})`,
    ...results.summary.map(
      (phase) =>
        `${phase.phase.padEnd(14)} mean ${phase.meanFps} fps, min ${phase.minFps}, ` +
        `${phase.secondsAtTarget}/${phase.seconds} s at ≥ ${results.targetFps}, longest gap ${phase.maxGapMs ?? "–"} ms`,
    ),
    ...results.errors.map((error) => `Error: ${error}`),
  ].join("\n");
}

// --- wiring ---

document.addEventListener("visibilitychange", () => {
  run?.visibility.push({ at: epochNow(), value: document.visibilityState });
});

const select = $<HTMLSelectElement>("mode");
for (const mode of MODES) {
  const option = document.createElement("option");
  option.value = mode.id;
  option.textContent = mode.supported() ? mode.label : `${mode.label} (not supported here)`;
  option.disabled = !mode.supported();
  select.append(option);
}
const describe = () => {
  $("mode-detail").textContent = MODES.find((mode) => mode.id === select.value)?.detail ?? "";
};
select.addEventListener("change", describe);
describe();

$("enable").addEventListener("click", () => {
  enableCamera().catch((error: unknown) => {
    $("camera-status").textContent =
      `Camera unavailable: ${error instanceof Error ? error.message : String(error)}`;
  });
});
$("start").addEventListener("click", () => void start(select.value as ModeId));
$("stop").addEventListener("click", () => void finish());
$("download").addEventListener("click", download);
$("protocol-length").textContent = `${PROTOCOL_SECONDS / 60} minutes`;
$("schedule").replaceChildren(
  ...PROTOCOL.map((phase) => {
    const item = document.createElement("li");
    item.textContent = `${phase.seconds} s: ${phase.instruction}`;
    return item;
  }),
);
window.setInterval(tick, 500);
