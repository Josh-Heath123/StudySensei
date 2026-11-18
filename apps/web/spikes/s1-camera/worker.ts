/**
 * Modes c–e: frames arrive from a MediaStreamTrackProcessor, ideally created here from a track
 * the page transferred in (else the page transfers the processor's readable stream). Each frame
 * is drawn small onto an OffscreenCanvas and run through the same workload as the main-thread
 * modes. Only numbers go back to the page: the frame is closed here and never leaves the worker.
 */
import { analyseFrame, WORK_HEIGHT, WORK_WIDTH } from "./metrics";

export type ToWorker =
  | { type: "start"; track: MediaStreamTrack }
  | { type: "start"; readable: ReadableStream<VideoFrame> }
  | { type: "stop" };

export type FromWorker =
  | { type: "started"; source: "transferred track" | "transferred stream" }
  | { type: "frame"; at: number; brightness: number; difference: number }
  | { type: "error"; message: string };

// A dedicated worker's global scope, typed by what's used (the DOM lib lacks the worker types).
const scope = self as unknown as {
  postMessage(message: FromWorker): void;
  onmessage: ((event: MessageEvent<ToWorker>) => void) | null;
};

const canvas = new OffscreenCanvas(WORK_WIDTH, WORK_HEIGHT);
const context = canvas.getContext("2d", { willReadFrequently: true });
let reader: ReadableStreamDefaultReader<VideoFrame> | null = null;
let track: MediaStreamTrack | null = null;

const epochNow = () => performance.timeOrigin + performance.now();

async function run(readable: ReadableStream<VideoFrame>): Promise<void> {
  if (!context) throw new Error("No 2D context on OffscreenCanvas");
  let previous: Float32Array | null = null;
  let current: Float32Array = new Float32Array(WORK_WIDTH * WORK_HEIGHT);
  reader = readable.getReader();
  for (;;) {
    const { value: frame, done } = await reader.read();
    if (done || !frame) return;
    try {
      context.drawImage(frame, 0, 0, WORK_WIDTH, WORK_HEIGHT);
    } finally {
      frame.close();
    }
    const { data } = context.getImageData(0, 0, WORK_WIDTH, WORK_HEIGHT);
    const stats = analyseFrame(data, previous, current);
    [previous, current] = [current, previous ?? new Float32Array(WORK_WIDTH * WORK_HEIGHT)];
    scope.postMessage({ type: "frame", at: epochNow(), ...stats });
  }
}

scope.onmessage = (event) => {
  const message = event.data;
  if (message.type === "stop") {
    void reader?.cancel();
    track?.stop();
    return;
  }
  let readable: ReadableStream<VideoFrame>;
  if ("track" in message) {
    track = message.track;
    readable = new MediaStreamTrackProcessor({ track }).readable;
    scope.postMessage({ type: "started", source: "transferred track" });
  } else {
    readable = message.readable;
    scope.postMessage({ type: "started", source: "transferred stream" });
  }
  run(readable).catch((error: unknown) =>
    scope.postMessage({
      type: "error",
      message: error instanceof Error ? error.message : String(error),
    }),
  );
};
