import { citedLabels } from "./citations";
import type { MessageMode, StoredMessage, StreamSource } from "./api";
import type { Quiz, QuizAnswers } from "./quiz";

export type AnswerStatus =
  "waiting" | "streaming" | "complete" | "truncated" | "failed" | "stopped";

export type SourceView = {
  label: string;
  /** Null once the material has been deleted (the citation still names it). */
  materialId: string | null;
  title: string;
  page: number;
  pageTitle: string | null;
  cited: boolean;
};

export type AnswerView = {
  text: string;
  status: AnswerStatus;
  sources: SourceView[];
  model: string | null;
  firstTokenMs: number | null;
  error: string | null;
  /** When the providers expect to take requests again (busy or out of quota). */
  retryAt: string | null;
  /** The stored message (null while it's still being written). */
  messageId: string | null;
  mode: MessageMode;
  /** "Quiz me": its questions and the picks so far. */
  quiz: Quiz | null;
  quizAnswers: QuizAnswers | null;
  totalMs: number | null;
  /** Asked by voice: release of push-to-talk to the first spoken word (measured). */
  voiceLatencyMs: number | null;
};

export type Turn = {
  key: string;
  question: string;
  mode: MessageMode;
  answer: AnswerView | null;
};

/** Stored messages as question-and-answer turns, oldest first. */
export function turnsFromMessages(messages: StoredMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (const message of messages) {
    if (message.role === "user") {
      turns.push({ key: message.id, question: message.text, mode: message.mode, answer: null });
      continue;
    }
    const turn = turns.at(-1);
    if (!turn || turn.answer) continue;
    turn.answer = {
      text: message.text,
      status: message.status,
      sources: message.sources.map((s) => ({
        label: s.label,
        materialId: s.material_id,
        title: s.material_title,
        page: s.page_number,
        pageTitle: s.page_title,
        cited: s.cited,
      })),
      model: message.model,
      firstTokenMs: message.first_token_ms,
      // A quiz that couldn't be used says why in its text; a streamed one just failed.
      error:
        message.status !== "failed"
          ? null
          : message.mode === "quiz" && message.text
            ? message.text
            : "The tutor couldn't answer this one.",
      retryAt: null,
      messageId: message.id,
      mode: message.mode,
      quiz: message.quiz ?? null,
      quizAnswers: message.quiz_answers ?? null,
      totalMs: message.total_ms,
      voiceLatencyMs: message.voice_latency_ms ?? null,
    };
  }
  return turns;
}

/** Sources as streamed, marked cited when the text so far cites them. */
export function liveSources(sources: StreamSource[], text: string, cited?: string[]): SourceView[] {
  const labels = new Set(cited ?? citedLabels(text));
  return sources.map((s) => ({
    label: s.label,
    materialId: s.material_id,
    title: s.material_title,
    page: s.page_number,
    pageTitle: s.page_title,
    cited: labels.has(s.label),
  }));
}

/** "groq/openai/gpt-oss-120b" → "gpt-oss-120b (Groq)". */
export function modelName(route: string): string {
  const [provider, ...rest] = route.split("/");
  const model = rest.at(-1) ?? route;
  if (!provider || rest.length === 0) return route;
  return `${model} (${provider.charAt(0).toUpperCase()}${provider.slice(1)})`;
}

/** "Answered by gpt-oss-120b (Groq) · first words in 0.6 s (measured)". */
export function answeredBy(model: string | null, firstTokenMs: number | null): string | null {
  if (model === null) return null;
  const by = `Answered by ${modelName(model)}`;
  if (firstTokenMs === null) return by;
  return `${by} · first words in ${(firstTokenMs / 1000).toFixed(1)} s (measured)`;
}

/** "Written by gpt-oss-120b (Groq) · in 3.4 s (measured)": a quiz arrives whole. */
export function writtenBy(model: string | null, totalMs: number | null): string | null {
  if (model === null) return null;
  const by = `Written by ${modelName(model)}`;
  if (totalMs === null) return by;
  return `${by} · in ${(totalMs / 1000).toFixed(1)} s (measured)`;
}

/** The readable message for an answer that couldn't be given. */
export function errorMessage(
  error: string,
  retryAt: string | null,
  formatTime: (date: Date) => string = (date) =>
    date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
): string {
  if (retryAt !== null) {
    return `The free AI providers are busy; try again at ${formatTime(new Date(retryAt))}.`;
  }
  return error;
}

/**
 * The answer split into finished sentences, for the screen-reader live region: it grows
 * one sentence at a time rather than one token at a time. While streaming, the last,
 * unfinished sentence is held back; once done, it's included.
 */
export function spokenSentences(text: string, finished: boolean): string[] {
  const sentences: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const char = text[i]!;
    const next = text[i + 1];
    // A sentence ends at a newline, or at . ! ? followed by whitespace ("3." may still
    // become "3.5", so a stop at the very end waits for what comes after it).
    const ends = char === "\n" || (/[.!?]/.test(char) && next !== undefined && /\s/.test(next));
    if (!ends) continue;
    const sentence = text.slice(start, i + 1).trim();
    if (sentence) sentences.push(sentence);
    start = i + 1;
  }
  if (finished && text.slice(start).trim()) sentences.push(text.slice(start).trim());
  return sentences;
}
