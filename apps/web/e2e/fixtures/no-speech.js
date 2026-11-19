// Injected into every e2e page except voice.spec.ts (which brings its own fakes), through
// e2e/test.ts. Headless Chromium's renderer crashes when SpeechRecognition.available() is
// called (seen 19 Nov 2026 with Chromium 158; headed Chromium answers "downloadable"), and
// the session screen asks it as soon as the tutor dock mounts. Without the API the tutor
// shows that voice is off, as in Firefox. Nothing here is part of the app.
(() => {
  for (const name of ["SpeechRecognition", "webkitSpeechRecognition"]) {
    Object.defineProperty(window, name, { value: undefined, configurable: true });
  }
})();
