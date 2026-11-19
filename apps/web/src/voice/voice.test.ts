import { fakeRecognitionClass, fakeSynth, LOCAL_VOICE, NETWORK_VOICE } from "@/test/fakeSpeech";

import {
  checkAvailability,
  installSpeechPack,
  listen,
  ON_DEVICE_ONLY,
  recognitionClass,
  supportsOnDevice,
} from "./stt";
import { spokenAfter, voiceTiming } from "./timing";
import { chooseVoice, localVoices, Speaker, speechText } from "./tts";

describe("stt: on-device only", () => {
  test.each([
    ["available", "available"],
    ["downloadable", "downloadable"],
    ["downloading", "unavailable"],
    ["unavailable", "unavailable"],
  ])("available() saying %s means %s", async (status, expected) => {
    const { cls } = fakeRecognitionClass({ status });

    expect(await checkAvailability("en-US", cls)).toBe(expected);
    expect(cls.available).toHaveBeenCalledWith({ langs: ["en-US"], processLocally: true });
  });

  test("a browser without the on-device API is unavailable, never 'try anyway'", async () => {
    const { cls, started } = fakeRecognitionClass({ onDevice: false });

    expect(supportsOnDevice(cls)).toBe(false);
    expect(await checkAvailability("en-US", cls)).toBe("unavailable");
    expect(() => listen("en-US", () => undefined, cls)).toThrow(ON_DEVICE_ONLY);
    expect(started).toEqual([]); // no recognition ever started (it would use a server)
  });

  test("no SpeechRecognition at all is unavailable", async () => {
    expect(recognitionClass({})).toBeNull();
    expect(await checkAvailability("en-US", null)).toBe("unavailable");
    expect(() => listen("en-US", () => undefined, null)).toThrow(ON_DEVICE_ONLY);
  });

  test("an availability check that throws is unavailable", async () => {
    const { cls } = fakeRecognitionClass();
    cls.available!.mockRejectedValueOnce(new Error("boom"));

    expect(await checkAvailability("en-US", cls)).toBe("unavailable");
  });

  test("installing the speech pack, and a failed install", async () => {
    const ok = fakeRecognitionClass({ status: "downloadable" });
    expect(await installSpeechPack("en-US", ok.cls)).toBe(true);
    expect(ok.cls.install).toHaveBeenCalledWith({ langs: ["en-US"], processLocally: true });
    expect(await checkAvailability("en-US", ok.cls)).toBe("available");

    const failing = fakeRecognitionClass({ status: "downloadable", installs: false });
    expect(await installSpeechPack("en-US", failing.cls)).toBe(false);
    failing.cls.install!.mockRejectedValueOnce(new Error("network"));
    expect(await installSpeechPack("en-US", failing.cls)).toBe(false);
  });

  test("every recognition starts with processLocally = true", () => {
    const fake = fakeRecognitionClass();

    listen("en-GB", () => undefined, fake.cls);

    expect(fake.last!.startedLocally).toBe(true);
    expect(fake.last!.lang).toBe("en-GB");
    expect(fake.last!.interimResults).toBe(true);
  });

  test("a browser that won't keep processLocally is refused before starting", () => {
    const fake = fakeRecognitionClass();
    Object.defineProperty(fake.cls.prototype, "processLocally", {
      get: () => false,
      set: () => undefined,
    });

    expect(() => listen("en-US", () => undefined, fake.cls)).toThrow(ON_DEVICE_ONLY);
    expect(fake.started).toEqual([]);
  });

  test("interim words as they're heard, then the final transcript", async () => {
    const fake = fakeRecognitionClass();
    const heard: string[] = [];
    const listening = listen("en-US", (text) => heard.push(text), fake.cls);

    fake.last!.hear("what is");
    fake.last!.hear("what is a salt", true);
    fake.last!.hear("for");
    const final = await listening.finish();

    expect(heard).toEqual(["what is", "what is a salt", "what is a salt for"]);
    expect(final).toBe("what is a salt for");
  });

  test("cancel throws the words away", async () => {
    const fake = fakeRecognitionClass();
    const listening = listen("en-US", () => undefined, fake.cls);
    fake.last!.hear("never mind", true);

    listening.cancel();

    expect(fake.last!.aborted).toBe(true);
  });

  test("a refused microphone reads plainly", async () => {
    const fake = fakeRecognitionClass();
    const listening = listen("en-US", () => undefined, fake.cls);
    fake.last!.fail("not-allowed");

    await expect(listening.finish()).rejects.toThrow("The microphone isn't allowed");
  });
});

describe("tts: local voices only", () => {
  test("network voices are never chosen", () => {
    const { synth } = fakeSynth();

    expect(localVoices(synth)).toEqual([LOCAL_VOICE]);
    expect(chooseVoice(synth.getVoices(), "en-US")).toBe(LOCAL_VOICE);
    expect(chooseVoice([NETWORK_VOICE], "en-US")).toBeNull();
  });

  test("the closest local voice for the language", () => {
    const za = { name: "ZA", lang: "en-ZA", localService: true };
    const fr = { name: "FR", lang: "fr-FR", localService: true, default: true };

    expect(chooseVoice([fr, za], "en-ZA")).toBe(za);
    expect(chooseVoice([fr, za], "en-GB")).toBe(za);
    expect(chooseVoice([fr], "en-GB")).toBe(fr);
  });

  test("spoken text has no Markdown, citations, tables or code", () => {
    const answer = [
      "## Salting",
      "A **salt** is random data [S1] added to each password【S2】, see [the notes](https://x.test).",
      "",
      "| Scheme | Salt |",
      "| --- | --- |",
      "| crypt | 12-bit |",
      "",
      "- It stops `rainbow` tables [S1, S3].",
      "```",
      "hash = H(salt + password)",
      "```",
      "The cost is $2^n$ guesses.",
    ].join("\n");

    const said = speechText(answer);

    expect(said).not.toMatch(/[[\]【】|*#`]|S1|S2|https/);
    expect(said).toContain("A salt is random data added to each password, see the notes.");
    expect(said).toContain("crypt, 12-bit.");
    expect(said).toContain("It stops rainbow tables.");
    expect(said).not.toContain("hash = H");
  });

  test("sentences are queued one by one as they complete, while the answer streams", () => {
    const { synth, utterance, spoken } = fakeSynth();
    const speaker = new Speaker(synth, utterance, LOCAL_VOICE);

    speaker.feed("A salt is random", false);
    expect(spoken).toEqual([]);
    speaker.feed("A salt is random data [S1]. It stops rain", false);
    expect(spoken.map((u) => u.text)).toEqual(["A salt is random data."]);
    speaker.feed("A salt is random data [S1]. It stops rainbow tables. And", false);
    speaker.feed("A salt is random data [S1]. It stops rainbow tables. And costs more", true);

    expect(spoken.map((u) => u.text)).toEqual([
      "A salt is random data.",
      "It stops rainbow tables.",
      "And costs more",
    ]);
    expect(spoken.every((u) => u.voice === LOCAL_VOICE)).toBe(true);
  });

  test("the first sentence and the first word are marked once", () => {
    const { synth, utterance, startSpeaking } = fakeSynth();
    const firstSentence = vi.fn();
    const firstWord = vi.fn();
    let now = 100;
    const speaker = new Speaker(
      synth,
      utterance,
      LOCAL_VOICE,
      { firstSentence, firstWord },
      () => now,
    );

    speaker.feed("One. Two. ", false);
    now = 250;
    startSpeaking(0);
    startSpeaking(1);

    expect(firstSentence).toHaveBeenCalledTimes(1);
    expect(firstSentence).toHaveBeenCalledWith(100);
    expect(firstWord).toHaveBeenCalledTimes(1);
    expect(firstWord).toHaveBeenCalledWith(250);
  });

  test("stop silences it for good", () => {
    const { synth, utterance, spoken } = fakeSynth();
    const speaker = new Speaker(synth, utterance, LOCAL_VOICE);
    speaker.feed("One. Two", false);
    expect(spoken).toHaveLength(1);

    speaker.stop();
    speaker.feed("One. Two. Three. ", true);

    expect(synth.cancel).toHaveBeenCalledTimes(1);
    expect(spoken).toHaveLength(1);
  });
});

describe("timing", () => {
  test("every part from the release, once all four marks are in", () => {
    const marks = { release: 1000, transcript: 1250, firstToken: 1900, firstSentence: 2500 };

    expect(voiceTiming(marks)).toBeNull();
    expect(voiceTiming({ ...marks, firstWord: 2900.4 })).toEqual({
      voice_latency_ms: 1900,
      transcript_ms: 250,
      first_token_ms: 900,
      first_sentence_ms: 1500,
    });
    // A mark before the release (clock jitter) is 0, never negative.
    expect(voiceTiming({ ...marks, transcript: 990, firstWord: 3000 })!.transcript_ms).toBe(0);
  });

  test("the footnote", () => {
    expect(spokenAfter(1900)).toBe("spoken after 1.9 s (measured)");
    expect(spokenAfter(2549)).toBe("spoken after 2.5 s (measured)");
  });
});
