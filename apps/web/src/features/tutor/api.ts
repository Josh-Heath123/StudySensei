import { useQuery } from "@tanstack/react-query";

import { API_URL, api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { ApiError, messageFromBody, unwrap } from "@/lib/api/errors";
import { readSse } from "@/lib/sse";

export type Conversation = components["schemas"]["ConversationOut"];
export type StoredMessage = components["schemas"]["MessageOut"];
export type StoredSource = components["schemas"]["MessageSourceOut"];
export type StreamSource = components["schemas"]["SourceOut"];
export type DoneEvent = components["schemas"]["DoneEvent"];
export type ErrorEvent = components["schemas"]["ErrorEvent"];
/** The modes that stream text (`quiz` has its own endpoint). */
export type TutorMode = NonNullable<components["schemas"]["MessageCreate"]["mode"]>;
/** Every mode a stored message can have. */
export type MessageMode = StoredMessage["mode"];

/** A request the API turned down, with when to try again if the AI was only busy. */
export class TutorRequestError extends ApiError {
  readonly retryAt: string | null;

  constructor(status: number, message: string, retryAt: string | null) {
    super(status, message);
    this.retryAt = retryAt;
  }
}

/** "Quiz me": the stored answer (its `quiz`, or `failed` with a readable `text`). */
export async function requestQuiz(conversationId: string): Promise<StoredMessage> {
  const { data, error, response } = await api.POST("/conversations/{conversation_id}/quiz", {
    params: { path: { conversation_id: conversationId } },
  });
  if (!response.ok || !data) {
    const wait = Number(response.headers.get("Retry-After"));
    const retryAt =
      response.status === 503 && Number.isFinite(wait) && wait > 0
        ? new Date(Date.now() + wait * 1000).toISOString()
        : null;
    throw new TutorRequestError(response.status, messageFromBody(error), retryAt);
  }
  return data;
}

/** Record a spoken question's latency on its answer (measured here, in the browser). */
export function saveVoiceTiming(
  messageId: string,
  timing: components["schemas"]["VoiceTimingIn"],
): Promise<StoredMessage> {
  return unwrap(
    api.PATCH("/messages/{message_id}/voice-timing", {
      params: { path: { message_id: messageId } },
      body: timing,
    }),
  );
}

/** Save the picks for a quiz (one per question, null if not answered yet). */
export function saveQuizAnswers(
  messageId: string,
  answers: (number | null)[],
): Promise<StoredMessage> {
  return unwrap(
    api.PATCH("/messages/{message_id}/quiz-answers", {
      params: { path: { message_id: messageId } },
      body: { answers },
    }),
  );
}

/** One event of an answer, in the order the API sends them (ARCHITECTURE "The tutor's stream"). */
export type TutorEvent =
  | { type: "sources"; sources: StreamSource[] }
  | { type: "delta"; text: string }
  | { type: "done"; done: DoneEvent }
  | { type: "error"; error: ErrorEvent };

export const conversationKey = (moduleId: string, sessionId: string | null) =>
  ["tutor", "session-conversation", moduleId, sessionId] as const;

/** The study session's conversation (its newest, if somehow there are more), or null. */
export function useSessionConversation(moduleId: string, sessionId: string | null) {
  return useQuery({
    queryKey: conversationKey(moduleId, sessionId),
    enabled: sessionId !== null,
    queryFn: async () => {
      const list = await unwrap(
        api.GET("/modules/{module_id}/tutor/conversations", {
          params: { path: { module_id: moduleId }, query: { study_session_id: sessionId } },
        }),
      );
      return list[0] ?? null;
    },
  });
}

export function createConversation(
  moduleId: string,
  body: { study_session_id: string; topic_id: string | null },
): Promise<Conversation> {
  return unwrap(
    api.POST("/modules/{module_id}/tutor/conversations", {
      params: { path: { module_id: moduleId } },
      body,
    }),
  );
}

/**
 * Ask, and read the answer's events as they stream. `signal` aborts the request: the
 * API then stops the provider and stores what was said as "stopped".
 *
 * Throws an `ApiError` for an HTTP error (404, 422) before the stream starts.
 */
export async function* streamAnswer(
  conversationId: string,
  body: { question: string; mode: TutorMode },
  signal: AbortSignal,
): AsyncGenerator<TutorEvent> {
  const response = await globalThis.fetch(
    new Request(`${API_URL}/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    }),
  );
  if (!response.ok || response.body === null) {
    const error = await response.json().catch(() => null);
    throw new ApiError(response.status, messageFromBody(error));
  }
  for await (const { event, data } of readSse(response.body)) {
    const payload: unknown = JSON.parse(data);
    if (event === "sources") {
      yield { type: "sources", sources: (payload as { sources: StreamSource[] }).sources };
    } else if (event === "delta") {
      yield { type: "delta", text: (payload as { text: string }).text };
    } else if (event === "done") {
      yield { type: "done", done: payload as DoneEvent };
    } else if (event === "error") {
      yield { type: "error", error: payload as ErrorEvent };
    }
  }
}
