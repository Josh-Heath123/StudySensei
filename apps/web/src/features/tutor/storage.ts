/** The tutor's per-browser conveniences in localStorage: never anything that must persist. */

/** Shown once, above the tutor's input, until the first question is asked. */
export const PRIVACY_NOTE =
  "Your question and the matching pages of your material go to a free AI provider. " +
  "Your reflections and personal details don't.";

const KEY = "studysensei.tutor.privacy-note-seen";

export function privacyNoteSeen(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function rememberPrivacyNote(): void {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    // Private mode: it shows again next time, which is harmless.
  }
}

// Whether the desktop panel is open (the student's last choice; open the first time).
const PANEL_KEY = "studysensei.tutor.panel-open";

export function panelOpenAtStart(): boolean {
  try {
    return localStorage.getItem(PANEL_KEY) !== "0";
  } catch {
    return true;
  }
}

export function rememberPanelOpen(open: boolean): void {
  try {
    localStorage.setItem(PANEL_KEY, open ? "1" : "0");
  } catch {
    // Private mode: the panel opens next time, which is harmless.
  }
}

// Whether answers to typed questions are read aloud (off unless the student turned it on).
const READ_ALOUD_KEY = "studysensei.tutor.read-aloud";

export function readAloudAtStart(): boolean {
  try {
    return localStorage.getItem(READ_ALOUD_KEY) === "1";
  } catch {
    return false;
  }
}

export function rememberReadAloud(on: boolean): void {
  try {
    localStorage.setItem(READ_ALOUD_KEY, on ? "1" : "0");
  } catch {
    // Private mode: it's off again next time, which is the default anyway.
  }
}
