# 0015: Voice is on-device only

- **Date:** 2026-11-19
- **Status:** Accepted. Replaces ARCHITECTURE's earlier plan for the microphone ("STT through an interface; the
  app says which vendor receives the audio").

## Context

Phase 3 adds asking the tutor by voice: speech to text, the streamed answer, then text to speech. The project's rule
is that camera frames and audio never leave the browser and are never stored. The earlier plan allowed a
vendor STT as long as the app named it, which would break that rule.

The browser's Web Speech API has two modes. Chrome's older `SpeechRecognition` sends the audio to Google's servers.
The newer on-device mode (`processLocally = true`, with `SpeechRecognition.available()` and `install()` for a
per-language speech pack) recognises on the device. `speechSynthesis` has the same split: some voices are network
voices (`localService === false`), so the text is sent to a server to be spoken.

## Decision

1. **Speech to text runs only on the device.** Every recognition is started with `processLocally = true`, and only
   after `SpeechRecognition.available({ langs, processLocally: true })` says `"available"`.
   - `"downloadable"`: the panel offers a one-time "Set up voice (downloads a speech pack to this device)", which
     calls `install()`.
   - Anything else, or a browser without `available`, `install` or `processLocally`, means no mic. One line says
     the browser can't recognise speech on the device, and typing works.
   - **There is no fallback to server recognition.** A browser that won't keep `processLocally = true` is refused
     before `start()`. Tests check both cases.
2. **Push-to-talk only.** Hold the mic button, or hold Space outside a text field or a focused control. Releasing
   sends the transcript, and Escape cancels. There's no always-on listening and no wake word.
3. **Text to speech uses local voices only** (`localService === true`). With none, "Read aloud" is hidden and one
   line says so.
4. **Only words leave the browser**, as the typed question would. No audio is sent or stored. The answer's
   voice latency and its parts are stored, as numbers only (migration 0020).

## Alternatives considered

| Option                                      | Why not                                                                                                                                             |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Server Web Speech (Chrome's default)        | Sends the audio to Google: breaks the rule                                                                                                          |
| A free STT API (Groq Whisper, Gemini audio) | Sends the audio to a provider; free tiers may keep it                                                                                               |
| Whisper in the browser (WASM or WebGPU)     | Keeps audio local but downloads a 40–150 MB model, and on a laptop CPU it's too slow for 2.5 s. Worth revisiting if on-device Web Speech stays rare |
| Network voices for TTS                      | Sends the answer text to a speech server. It isn't personal data, but local voices are enough                                                       |

## Consequences

- Voice works only in a browser with on-device Web Speech: Chrome or Edge, with the speech pack installed. Other
  browsers (Firefox, Safari today) keep typing. PRODUCT says so.
- On 19 Nov on the owner's machine, Edge 157 said `"unavailable"` for en-GB and en-US. Playwright's Chromium 158
  said `"downloadable"`. Chrome wasn't installed.
- The 2.5 s target is measured in the browser on every spoken question, from release to the first spoken word. It's
  shown beside the answer as "spoken after 1.9 s (measured)" and stored on it.
- Swapping in another on-device engine later (in-browser Whisper) means a new `voice/stt.ts` behind the same
  `listen()`, and a new ADR if anything leaves the device.
