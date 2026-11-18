# Spike S1: camera in the browser

**Question:** can the browser keep processing webcam frames at a useful rate (≥ 5 a second) while the StudySensei tab
is in the background, hidden, or the window is minimised? And which technique makes that hold?

This is a measurement tool, not a feature. It's not in the app's bundle or routes. Tauri is the fallback (ROADMAP
spike S1), and nothing is built for it unless the browser results fail.

## Privacy

Camera frames never leave the browser. Each frame is scaled to 160×120, reduced to two numbers (mean brightness and
the mean difference from the previous frame, a stand-in for face detection, with no ML libraries), and dropped.
Nothing is uploaded or stored. The only output is the JSON file you choose to download, which holds timings,
visibility and the browser's name and version, never images.

## Running it

1. From the repo root: `npm run spike:s1`, then open http://localhost:5175 in the browser to test (Chrome or Edge:
   modes c–e need Chromium APIs). Close other tabs that play sound.
2. Click **Allow camera** once.
3. For each mode, in turn:
   1. Choose it and click **Start run**. The protocol panel turns into clock times; a phone timer helps, because you
      can't see the page while it's hidden.
   2. Follow the protocol, about 3 minutes in total:
      - **30 s visible**: keep the tab in front;
      - **60 s on another tab**: switch to another tab in the same window;
      - **60 s minimised**: minimise the browser window;
      - **30 s visible again**: restore it and bring the tab back.
   3. When the run ends (or after **Stop early**), click **Download results**. The file is
      `s1-camera-<mode>-<time>.json`.
4. Send the five files for review. Re-run a mode if a phase was missed; the phases are marked in the data by time, so
   the data is only as good as the timing.

## Modes

| Mode | Technique | Expectation to test |
| --- | --- | --- |
| a | Main thread, `requestVideoFrameCallback` on a `<video>` | Hidden tabs may stop rendering video, so callbacks may stop |
| b | Main thread, `setInterval` at 100 ms | Background timers are throttled (to about once a second, or less after a while) |
| c | A Web Worker fed by `MediaStreamTrackProcessor`, with the track transferred to the worker | Frames arrive from the camera, not from rendering or timers |
| d | Mode c plus a Document Picture-in-Picture window with a preview and the countdown | Keeps something of the page visible on top |
| e | Mode c plus a Web Lock held for the run | See the risk below |

Mode c records whether the track itself was transferred to the worker (`frameSource: "worker, transferred track"`) or,
where that isn't supported, the processor's stream (`"worker, transferred stream"`).

**Keep-alive risk (mode e):** Chrome's tab-freezing heuristics leave out pages that hold a Web Lock. That's a
documented heuristic, not a guarantee, and it can change; if only mode e holds the rate, the design would depend on
it. An "audible silence" trick isn't used: silent audio isn't documented as keeping a tab running, and real audio
would change what's being measured.

Note that an active camera capture may itself exempt the tab from some throttling, which this spike measures rather
than assumes.

## What's recorded

Every processed frame's time, every visibility change and every PiP open or close, all as timestamps. They're turned
into one sample per second when the run ends (`metrics.ts`, unit-tested), so the page's own throttled timers don't
distort the data. Per second: frames processed, the mean and longest gap between frames, `document.visibilityState`,
whether the PiP window was open, and the protocol phase. The file also has a per-phase summary (mean and minimum frames
a second, seconds at ≥ 5, longest gap), the browser and version, the OS, the mode, and any errors.

## Files

- `index.html`, `main.ts`: the page, the modes, the protocol and the download.
- `worker.ts`: modes c–e.
- `metrics.ts` (+ `metrics.test.ts`): the workload, phase marking and per-second aggregation.
- `vite.config.ts`: the spike's own entry on port 5175.
