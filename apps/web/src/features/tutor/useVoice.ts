import { useCallback, useEffect, useRef, useState } from "react";

import {
  checkAvailability,
  installSpeechPack,
  listen,
  recognitionClass,
  speechLang,
  type Listening,
} from "@/voice/stt";
import { voiceTiming, type VoiceMarks } from "@/voice/timing";
import { browserSynth, chooseVoice, Speaker, type VoiceLike } from "@/voice/tts";

import { readAloudAtStart, rememberReadAloud } from "./storage";
import type { useTutor } from "./useTutor";

type Tutor = ReturnType<typeof useTutor>;

export type MicState =
  "checking" | "available" | "downloadable" | "installing" | "install-failed" | "unavailable";

/** Marks the mic button, the one control where Space still means "talk". */
export const PUSH_TO_TALK = "data-push-to-talk";

/**
 * Where Space keeps its usual job: typing in a text field, or pressing a focused control
 * (a button, link, checkbox…). Anywhere else (or on the mic button), holding Space talks.
 */
export function spaceBelongsTo(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.closest(`[${PUSH_TO_TALK}]`)) return false;
  if (target.isContentEditable) return true;
  return (
    target.closest(
      "input, textarea, select, button, a[href], summary, [role=button], [role=checkbox], [role=switch], [role=radio], [role=tab], [role=menuitem], [role=option]",
    ) !== null
  );
}

/** The answer being spoken, and (asked by voice) its latency marks. */
type SpeakerEntry = { id: number; speaker: Speaker; marks: VoiceMarks | null; reported: boolean };

const NOTHING_HEARD = "Didn't catch that. Hold the button (or Space) while you speak.";

/**
 * Voice for the tutor (decision 0015): push-to-talk on the device only, answers read aloud
 * with local voices only, and the latency of a spoken question measured from release to
 * the first spoken word. Lives beside `useTutor` in the dock, so it outlives the panel.
 * `spaceToTalk`: the panel is showing, so holding Space talks.
 */
export function useVoice(tutor: Tutor, { spaceToTalk }: { spaceToTalk: boolean }) {
  const lang = speechLang();
  const [mic, setMic] = useState<MicState>("checking");
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [readAloud, setReadAloudState] = useState(readAloudAtStart);
  const [voice, setVoice] = useState<VoiceLike | null>(null);
  const [voicesChecked, setVoicesChecked] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const session = useRef<Listening | null>(null);
  const viaSpace = useRef(false);
  // The marks for the next question, set when push-to-talk is released.
  const pending = useRef<VoiceMarks | null>(null);
  const speaker = useRef<SpeakerEntry | null>(null);
  // An answer whose speech was stopped is never started again.
  const silenced = useRef<number | null>(null);
  const currentId = useRef<number | null>(null);
  const synth = useRef(browserSynth());
  useEffect(() => {
    currentId.current = tutor.current?.id ?? null;
  });

  // Is on-device recognition here? Asked once.
  useEffect(() => {
    let live = true;
    void checkAvailability(lang).then((found) => live && setMic(found));
    return () => {
      live = false;
    };
  }, [lang]);

  // Local voices can arrive after the page loads: wait for them a moment before saying
  // there are none.
  useEffect(() => {
    const found = synth.current;
    if (!found) {
      setVoicesChecked(true);
      return;
    }
    const pick = (final: boolean) => {
      const voices = found.synth.getVoices();
      setVoice(chooseVoice(voices, lang));
      if (final || voices.length > 0) setVoicesChecked(true);
    };
    pick(false);
    const changed = () => pick(true);
    const target = found.synth as unknown as Partial<EventTarget>;
    target.addEventListener?.("voiceschanged", changed);
    const wait = setTimeout(changed, 1500);
    return () => {
      clearTimeout(wait);
      target.removeEventListener?.("voiceschanged", changed);
    };
  }, [lang]);

  // Stop the answer being spoken, for good (the Speaker reports idle, so speaking goes
  // false through its callback).
  const silence = useCallback(() => {
    silenced.current = speaker.current?.id ?? currentId.current;
    speaker.current?.speaker.stop();
    speaker.current = null;
  }, []);
  const stopSpeaking = useCallback(() => {
    silence();
    setSpeaking(false);
  }, [silence]);

  // Leaving the session stops listening and speaking.
  useEffect(
    () => () => {
      session.current?.cancel();
      session.current = null;
      speaker.current?.speaker.stop();
    },
    [],
  );

  const install = useCallback(async () => {
    setMic("installing");
    const ok = await installSpeechPack(lang);
    setMic(ok ? await checkAvailability(lang) : "install-failed");
  }, [lang]);

  const start = useCallback(() => {
    if (mic !== "available" || session.current || !tutor.ready || tutor.busy) return;
    stopSpeaking();
    setError(null);
    setInterim("");
    try {
      session.current = listen(lang, setInterim, recognitionClass());
      setListening(true);
    } catch (failed) {
      setError((failed as Error).message);
    }
  }, [mic, lang, tutor.ready, tutor.busy, stopSpeaking]);

  const cancel = useCallback(() => {
    session.current?.cancel();
    session.current = null;
    viaSpace.current = false;
    setListening(false);
    setInterim("");
  }, []);

  const { send } = tutor;
  const release = useCallback(async () => {
    const current = session.current;
    if (!current) return;
    session.current = null;
    const released = performance.now();
    setListening(false);
    let text: string;
    try {
      text = await current.finish();
    } catch (failed) {
      setError((failed as Error).message);
      setInterim("");
      return;
    }
    setInterim("");
    if (!text) {
      setError(NOTHING_HEARD);
      return;
    }
    pending.current = { release: released, transcript: performance.now() };
    void send(text, "answer", { voice: true });
  }, [send]);

  // Escape cancels a recognition, however it was started.
  useEffect(() => {
    if (!listening) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      cancel();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [listening, cancel]);

  // Hold Space to talk, unless Space belongs to a text field or a focused control.
  useEffect(() => {
    if (!spaceToTalk || mic !== "available") return;
    const down = (event: KeyboardEvent) => {
      if (event.code !== "Space" || spaceBelongsTo(event.target)) return;
      event.preventDefault();
      if (event.repeat || session.current) return;
      viaSpace.current = true;
      start();
    };
    const up = (event: KeyboardEvent) => {
      if (event.code !== "Space" || !viaSpace.current) return;
      event.preventDefault();
      viaSpace.current = false;
      void release();
    };
    document.addEventListener("keydown", down);
    document.addEventListener("keyup", up);
    return () => {
      document.removeEventListener("keydown", down);
      document.removeEventListener("keyup", up);
    };
  }, [spaceToTalk, mic, start, release]);

  // Speak the current answer as it streams: when it was asked by voice, or Read aloud is on.
  const current = tutor.current;
  const found = synth.current;
  const { recordVoiceTiming } = tutor;
  useEffect(() => {
    if (!current || current.mode === "quiz") return;
    if (speaker.current && speaker.current.id !== current.id) silence();
    const wanted = (current.voice || readAloud) && voice !== null && found !== null;
    if (!wanted || silenced.current === current.id) return;
    if (current.status === "stopped" || current.status === "failed") {
      silence();
      return;
    }
    if (!speaker.current) {
      if (!current.text) return;
      const marks = current.voice ? pending.current : null;
      pending.current = null;
      const entry: SpeakerEntry = {
        id: current.id,
        marks,
        reported: false,
        speaker: new Speaker(found.synth, found.utterance, voice, {
          firstSentence: (at) => {
            if (entry.marks) entry.marks.firstSentence ??= at;
          },
          firstWord: (at) => {
            if (entry.marks) entry.marks.firstWord ??= at;
            setSpeaking(true);
            report();
          },
          idle: () => setSpeaking(false),
        }),
      };
      speaker.current = entry;
    }
    const entry = speaker.current;
    if (entry.marks && current.firstTokenAt !== null) {
      entry.marks.firstToken ??= current.firstTokenAt;
    }
    entry.speaker.feed(
      current.text,
      current.status !== "waiting" && current.status !== "streaming",
    );
    report();

    // Once every mark is in and the answer has its id, store the timing (once).
    function report() {
      const messageId = current?.done?.message_id;
      if (!entry?.marks || entry.reported || !messageId) return;
      const timing = voiceTiming(entry.marks);
      if (!timing) return;
      entry.reported = true;
      void recordVoiceTiming(messageId, timing).catch(() => undefined);
    }
  });

  const setReadAloud = useCallback(
    (on: boolean) => {
      setReadAloudState(on);
      rememberReadAloud(on);
      // Off stops the answer being read; on applies from the next answer (never re-reads one).
      if (!on) stopSpeaking();
      else if (!speaker.current) silenced.current = currentId.current;
    },
    [stopSpeaking],
  );

  return {
    mic,
    listening,
    interim,
    error,
    install,
    start,
    release,
    cancel,
    /** A local voice exists, so answers can be read aloud. */
    canSpeak: voice !== null,
    voicesChecked,
    readAloud,
    setReadAloud,
    speaking,
    stopSpeaking,
  };
}
