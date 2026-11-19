/**
 * Text to speech, with this device's own voices only (decision 0015). Some browsers list
 * network voices that send the text to a server (`localService === false`): those are
 * never used. The answer is spoken a sentence at a time, as each sentence completes, so
 * speech can start before the answer has finished streaming.
 */
import { CITATION } from "@/features/tutor/citations";
import { spokenSentences } from "@/features/tutor/turns";

export interface VoiceLike {
  name: string;
  lang: string;
  localService: boolean;
  default?: boolean;
}

export interface UtteranceLike {
  voice: VoiceLike | null;
  lang: string;
  onstart: (() => void) | null;
  onend?: (() => void) | null;
  onerror?: (() => void) | null;
}

export interface SynthLike {
  speak(utterance: UtteranceLike): void;
  cancel(): void;
  getVoices(): VoiceLike[];
}

export type MakeUtterance = (text: string) => UtteranceLike;

export function browserSynth(): { synth: SynthLike; utterance: MakeUtterance } | null {
  if (typeof speechSynthesis === "undefined" || typeof SpeechSynthesisUtterance === "undefined") {
    return null;
  }
  return {
    synth: speechSynthesis as unknown as SynthLike,
    utterance: (text) => new SpeechSynthesisUtterance(text) as unknown as UtteranceLike,
  };
}

/** The voices that run on this device. */
export function localVoices(synth: SynthLike): VoiceLike[] {
  return synth.getVoices().filter((voice) => voice.localService === true);
}

/** A local voice for `lang`: the same language and region, then the same language, then the
 * default local voice, then any local voice. Null when there's no local voice. */
export function chooseVoice(voices: VoiceLike[], lang: string): VoiceLike | null {
  const local = voices.filter((voice) => voice.localService === true);
  const base = lang.split("-")[0]!.toLowerCase();
  return (
    local.find((v) => v.lang.toLowerCase() === lang.toLowerCase()) ??
    local.find((v) => v.lang.toLowerCase().split("-")[0] === base) ??
    local.find((v) => v.default) ??
    local[0] ??
    null
  );
}

/**
 * What should be said for an answer's Markdown: the words only. No citation labels
 * ([S1], 【S2】, [S1, S3]), no Markdown markers, tables read as their cells, code blocks and
 * display maths left out, links as their text.
 */
export function speechText(markdown: string): string {
  return (
    markdown
      // Code blocks and display maths aren't read out.
      .replace(/```[\s\S]*?(```|$)/g, " ")
      .replace(/\$\$[\s\S]*?(\$\$|$)/g, " ")
      .replace(new RegExp(CITATION.source, "g"), "")
      // Table separator rows go; other rows become their cells, read as a sentence.
      .replace(/^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/gm, "")
      .replace(/^\s*\|(.*)\|\s*$/gm, (_, cells: string) =>
        cells
          .split("|")
          .map((cell) => cell.trim())
          .filter(Boolean)
          .join(", ")
          .concat("."),
      )
      // Images and links keep their words.
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      // Headings, quotes, list markers at the start of a line.
      .replace(/^[ \t]*(?:>[ \t]?)*(?:#{1,6}[ \t]+|[-*+][ \t]+|\d+[.)][ \t]+)?/gm, "")
      // Inline maths keeps its words; emphasis and code lose their markers.
      .replace(/\$([^$\n]+)\$/g, (_, tex: string) => tex.replace(/\\[a-zA-Z]+|[{}\\^_]/g, " "))
      .replace(/(\*\*|__|\*|_|`+)(?=\S)([^\n]*?\S)\1/g, "$2")
      .replace(/[ \t]+/g, " ")
      .replace(/ +([.,;:!?])/g, "$1")
      .trim()
  );
}

/**
 * Speaks one answer as it streams. `feed` it the answer so far; each sentence is queued
 * once, as soon as it's complete. `stop` silences it for good.
 */
export class Speaker {
  private queued = 0;
  private started = false;
  private stopped = false;

  constructor(
    private readonly synth: SynthLike,
    private readonly makeUtterance: MakeUtterance,
    private readonly voice: VoiceLike,
    private readonly on: {
      /** The first sentence was queued (it was complete). */
      firstSentence?: (at: number) => void;
      /** The first word was spoken (the first utterance started). */
      firstWord?: (at: number) => void;
      /** Everything fed has been said (or the speaker was stopped). */
      idle?: () => void;
    } = {},
    private readonly now: () => number = () => performance.now(),
  ) {}

  private pending = 0;
  private finished = false;

  private settle(): void {
    if (this.finished && this.pending === 0) this.on.idle?.();
  }

  feed(markdown: string, finished: boolean): void {
    if (this.stopped) return;
    this.finished = finished;
    const sentences = spokenSentences(speechText(markdown), finished);
    for (; this.queued < sentences.length; this.queued++) {
      const text = sentences[this.queued]!;
      if (!/\w/.test(text)) continue;
      const utterance = this.makeUtterance(text);
      utterance.voice = this.voice;
      utterance.lang = this.voice.lang;
      utterance.onstart = () => {
        if (this.started || this.stopped) return;
        this.started = true;
        this.on.firstWord?.(this.now());
      };
      if (!this.anyQueued) this.on.firstSentence?.(this.now());
      this.anyQueued = true;
      this.pending += 1;
      utterance.onend = utterance.onerror = () => {
        this.pending = Math.max(0, this.pending - 1);
        this.settle();
      };
      this.synth.speak(utterance);
    }
    this.settle();
  }

  private anyQueued = false;

  get speaking(): boolean {
    return this.anyQueued && !this.stopped;
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.synth.cancel();
    this.on.idle?.();
  }
}
