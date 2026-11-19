/**
 * Voice latency: from releasing push-to-talk to the first spoken word of the answer, and
 * its parts. The Phase 3 target is speech starting within 2.5 s. Times are
 * `performance.now()` readings in the same page, so they're comparable.
 */

export type VoiceMarks = {
  /** Push-to-talk released. */
  release: number;
  /** The final transcript came back. */
  transcript?: number;
  /** The answer's first token arrived. */
  firstToken?: number;
  /** Its first full sentence was queued for speech. */
  firstSentence?: number;
  /** The first word was spoken (the first utterance's onstart). */
  firstWord?: number;
};

export type VoiceTiming = {
  voice_latency_ms: number;
  transcript_ms: number;
  first_token_ms: number;
  first_sentence_ms: number;
};

export const SPEECH_TARGET_MS = 2500;

const since = (release: number, at: number) => Math.max(0, Math.round(at - release));

/** The timing once every mark is in; null until then. */
export function voiceTiming(marks: VoiceMarks): VoiceTiming | null {
  const { release, transcript, firstToken, firstSentence, firstWord } = marks;
  if (
    transcript === undefined ||
    firstToken === undefined ||
    firstSentence === undefined ||
    firstWord === undefined
  ) {
    return null;
  }
  return {
    voice_latency_ms: since(release, firstWord),
    transcript_ms: since(release, transcript),
    first_token_ms: since(release, firstToken),
    first_sentence_ms: since(release, firstSentence),
  };
}

/** "spoken after 1.9 s (measured)". */
export function spokenAfter(ms: number): string {
  return `spoken after ${(ms / 1000).toFixed(1)} s (measured)`;
}
