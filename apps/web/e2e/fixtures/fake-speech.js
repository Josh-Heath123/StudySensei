// Injected with page.addInitScript before the app loads (voice.spec.ts): on-device
// SpeechRecognition and speechSynthesis fakes, so the e2e run needs no microphone and no
// speech pack. Nothing here is part of the app. Driven from the spec through
// window.__speech: hear(text, final) plays recognised words; spoken lists the utterances.
(() => {
  const state = { recognitions: [], spoken: [], cancels: 0 };

  class FakeRecognition {
    constructor() {
      this.lang = "";
      this.continuous = false;
      this.interimResults = false;
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      this.results = [];
    }
    static available() {
      return Promise.resolve("available");
    }
    static install() {
      return Promise.resolve(true);
    }
    start() {
      this.startedLocally = this.processLocally;
      state.recognitions.push(this);
    }
    stop() {
      setTimeout(() => this.onend && this.onend(), 30);
    }
    abort() {
      setTimeout(() => this.onend && this.onend(), 0);
    }
  }
  Object.defineProperty(FakeRecognition.prototype, "processLocally", {
    value: false,
    writable: true,
    configurable: true,
  });

  const voices = [
    { name: "Network voice", lang: "en-US", localService: false, default: true },
    { name: "Local voice", lang: "en-US", localService: true, default: false },
  ];
  const synth = {
    speak(utterance) {
      state.spoken.push(utterance.text);
      const first = state.spoken.length === 1;
      // The device starts talking a moment after it's asked to.
      setTimeout(() => utterance.onstart && utterance.onstart(), first ? 120 : 0);
      setTimeout(() => utterance.onend && utterance.onend(), 400);
    },
    cancel() {
      state.cancels += 1;
    },
    getVoices: () => voices,
    addEventListener() {},
    removeEventListener() {},
  };
  function FakeUtterance(text) {
    this.text = text;
    this.voice = null;
    this.lang = "";
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
  }

  Object.defineProperty(window, "SpeechRecognition", { value: FakeRecognition });
  Object.defineProperty(window, "webkitSpeechRecognition", { value: FakeRecognition });
  Object.defineProperty(window, "speechSynthesis", { value: synth });
  Object.defineProperty(window, "SpeechSynthesisUtterance", { value: FakeUtterance });

  window.__speech = {
    state,
    hear(text, final) {
      const recognition = state.recognitions[state.recognitions.length - 1];
      const last = recognition.results[recognition.results.length - 1];
      if (last && !last.isFinal) recognition.results.pop();
      recognition.results.push({ isFinal: final, 0: { transcript: text } });
      recognition.onresult({ resultIndex: 0, results: recognition.results });
    },
  };
})();
