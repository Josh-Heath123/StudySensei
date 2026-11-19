/**
 * Speech to text, on this device only (decision 0015): audio never leaves the browser.
 *
 * It uses the Web Speech API's on-device recognition (`processLocally`). A browser that
 * doesn't have that API isn't offered voice at all: an older `SpeechRecognition` would
 * quietly ignore `processLocally` and send the audio to a server, so its absence is
 * treated as "unavailable", never as "try anyway".
 */

/** The parts of a result list the transcript needs. */
type ResultList = ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;

export interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  processLocally: boolean;
  onresult: ((event: { resultIndex: number; results: ResultList }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type Options = { langs: string[]; processLocally: boolean };

export interface RecognitionClass {
  new (): RecognitionLike;
  prototype: object;
  available?(options: Options): Promise<string>;
  install?(options: Options): Promise<boolean>;
}

export type Availability = "available" | "downloadable" | "unavailable";

export const ON_DEVICE_ONLY =
  "Voice works only with on-device speech recognition, which this browser doesn't offer.";

/** The browser's SpeechRecognition class, if any. */
export function recognitionClass(scope: object = globalThis): RecognitionClass | null {
  const found = scope as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown };
  const cls = found.SpeechRecognition ?? found.webkitSpeechRecognition;
  return typeof cls === "function" ? (cls as RecognitionClass) : null;
}

/** Whether the class can promise on-device recognition: `available`, `install` and
 * `processLocally` all exist. Without them, nothing is started. */
export function supportsOnDevice(
  cls: RecognitionClass | null,
): cls is RecognitionClass & Required<Pick<RecognitionClass, "available" | "install">> {
  return (
    cls !== null &&
    typeof cls.available === "function" &&
    typeof cls.install === "function" &&
    "processLocally" in cls.prototype
  );
}

/** The language to listen in: the browser's, or English. */
export function speechLang(): string {
  return (typeof navigator !== "undefined" && navigator.language) || "en-US";
}

/**
 * Can this device recognise speech in `lang` on its own? "available" (yes),
 * "downloadable" (after a one-time speech-pack install), or "unavailable" (anything
 * else, including a browser without the on-device API, or an error asking).
 */
export async function checkAvailability(
  lang: string,
  cls: RecognitionClass | null = recognitionClass(),
): Promise<Availability> {
  if (!supportsOnDevice(cls)) return "unavailable";
  try {
    const status = await cls.available({ langs: [lang], processLocally: true });
    return status === "available" || status === "downloadable" ? status : "unavailable";
  } catch {
    return "unavailable";
  }
}

/** Download the speech pack for `lang` to this device. True when it installed. */
export async function installSpeechPack(
  lang: string,
  cls: RecognitionClass | null = recognitionClass(),
): Promise<boolean> {
  if (!supportsOnDevice(cls)) return false;
  try {
    return (await cls.install({ langs: [lang], processLocally: true })) === true;
  } catch {
    return false;
  }
}

/** A recognition in progress: finish (keep the words) or cancel (drop them). */
export type Listening = {
  /** Stop listening and get the final transcript ("" if nothing was heard). */
  finish(): Promise<string>;
  /** Stop listening and throw the words away. */
  cancel(): void;
};

const ERRORS: Record<string, string> = {
  "not-allowed": "The microphone isn't allowed for this site. Check the browser's permissions.",
  "audio-capture": "No microphone was found.",
  "language-not-supported": "This language isn't available for on-device recognition.",
};

/**
 * Start listening, on the device only. `onInterim` gets the words so far as they're heard.
 * Throws `ON_DEVICE_ONLY` rather than ever starting a recognition that could use a server.
 */
export function listen(
  lang: string,
  onInterim: (text: string) => void,
  cls: RecognitionClass | null = recognitionClass(),
): Listening {
  if (!supportsOnDevice(cls)) throw new Error(ON_DEVICE_ONLY);
  const recognition = new cls();
  recognition.processLocally = true;
  // A browser that won't keep it would recognise on a server: never start that one.
  if (recognition.processLocally !== true) throw new Error(ON_DEVICE_ONLY);
  recognition.lang = lang;
  recognition.continuous = true;
  recognition.interimResults = true;

  let finals = "";
  let interim = "";
  let cancelled = false;
  let settle: { resolve: (text: string) => void; reject: (error: Error) => void } | null = null;
  let ended = false;
  let failure: Error | null = null;
  const words = () => `${finals} ${interim}`.replace(/\s+/g, " ").trim();

  recognition.onresult = (event) => {
    // The list holds every result so far (continuous mode): rebuild from all of it, so a
    // final is never counted twice.
    finals = "";
    interim = "";
    for (let i = 0; i < event.results.length; i++) {
      const result = event.results[i]!;
      if (result.isFinal) finals += ` ${result[0].transcript}`;
      else interim += ` ${result[0].transcript}`;
    }
    if (!cancelled) onInterim(words());
  };
  recognition.onerror = (event) => {
    if (event.error === "no-speech" || event.error === "aborted") return;
    failure = new Error(ERRORS[event.error] ?? `Speech recognition failed (${event.error}).`);
  };
  recognition.onend = () => {
    ended = true;
    if (!settle) return;
    if (failure) settle.reject(failure);
    else settle.resolve(cancelled ? "" : words());
  };
  recognition.start();

  return {
    finish() {
      return new Promise<string>((resolve, reject) => {
        settle = { resolve, reject };
        if (ended) {
          if (failure) reject(failure);
          else resolve(words());
          return;
        }
        recognition.stop();
      });
    },
    cancel() {
      cancelled = true;
      recognition.abort();
    },
  };
}
