/**
 * Fakes of the Web Speech API for tests: on-device recognition (with `available` and
 * `install`) and speechSynthesis. Tests drive them by hand: `FakeRecognition.last` is the
 * recognition the code started, and `hear` / `end` play what the browser would do.
 */
import { vi } from "vitest";

import type { RecognitionLike } from "@/voice/stt";
import type { SynthLike, UtteranceLike, VoiceLike } from "@/voice/tts";

type Result = { isFinal: boolean; 0: { transcript: string } };

export function fakeRecognitionClass({
  status = "available",
  installs = true,
  onDevice = true,
}: {
  /** What `available()` answers. */
  status?: string;
  /** Whether `install()` succeeds (and `available()` then says "available"). */
  installs?: boolean;
  /** False: an older browser, with no `processLocally`, `available` or `install`. */
  onDevice?: boolean;
} = {}) {
  let current = status;
  const started: FakeRecognition[] = [];

  class FakeRecognition implements RecognitionLike {
    // Declared, not initialised: it lives on the prototype only when the browser has it.
    declare processLocally: boolean;
    lang = "";
    continuous = false;
    interimResults = false;
    onresult: RecognitionLike["onresult"] = null;
    onerror: RecognitionLike["onerror"] = null;
    onend: RecognitionLike["onend"] = null;
    running = false;
    aborted = false;
    /** processLocally at the moment start() was called. */
    startedLocally: boolean | undefined;
    private results: Result[] = [];

    start() {
      this.startedLocally = (this as { processLocally?: boolean }).processLocally;
      this.running = true;
      started.push(this);
    }
    stop() {
      this.running = false;
      queueMicrotask(() => this.onend?.());
    }
    abort() {
      this.running = false;
      this.aborted = true;
      queueMicrotask(() => {
        this.onerror?.({ error: "aborted" });
        this.onend?.();
      });
    }
    /** The browser heard words (`final` when it's sure of them). */
    hear(transcript: string, final = false) {
      const last = this.results.at(-1);
      if (last && !last.isFinal) this.results.pop();
      this.results.push({ isFinal: final, 0: { transcript } });
      this.onresult?.({ resultIndex: 0, results: this.results });
    }
    fail(error: string) {
      this.onerror?.({ error });
      this.running = false;
      this.onend?.();
    }
  }
  if (onDevice) {
    Object.defineProperty(FakeRecognition.prototype, "processLocally", {
      value: false,
      writable: true,
      configurable: true,
    });
  }
  const statics = onDevice
    ? {
        available: vi.fn(async () => current),
        install: vi.fn(async () => {
          if (installs) current = "available";
          return installs;
        }),
      }
    : {};
  const cls = Object.assign(FakeRecognition, statics);
  return {
    cls,
    started,
    get last() {
      return started.at(-1);
    },
  };
}

/** A device's voices: a local one, and a network one that must never be used. */
export const LOCAL_VOICE: VoiceLike = { name: "Local English", lang: "en-US", localService: true };
export const NETWORK_VOICE: VoiceLike = {
  name: "Google US English",
  lang: "en-US",
  localService: false,
  default: true,
};

export function fakeSynth(voices: VoiceLike[] = [NETWORK_VOICE, LOCAL_VOICE]) {
  const spoken: (UtteranceLike & { text: string })[] = [];
  const synth: SynthLike & { cancel: ReturnType<typeof vi.fn<() => void>> } = {
    speak: (utterance) => spoken.push(utterance as UtteranceLike & { text: string }),
    cancel: vi.fn<() => void>(),
    getVoices: () => voices,
  };
  const utterance = (text: string) => ({ text, voice: null, lang: "", onstart: null });
  /** The browser starts saying the queued utterance at `index`. */
  const startSpeaking = (index = 0) => spoken[index]?.onstart?.();
  return { synth, utterance, spoken, startSpeaking };
}
