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
export type TutorMode = components["schemas"]["MessageCreate"]["mode"];

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
