import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

import type { ActiveSession } from "./controller";

export type ReflectionInput = components["schemas"]["ReflectionIn"];

/** The open session with its events, or null. Throws when the server can't be reached. */
export async function fetchActiveSession(): Promise<ActiveSession | null> {
  return (await unwrap(api.GET("/sessions/active"))) ?? null;
}

export function useSaveReflection() {
  return useMutation({
    mutationFn: ({ sessionId, body }: { sessionId: string; body: ReflectionInput }) =>
      unwrap(
        api.PUT("/sessions/{session_id}/reflection", {
          params: { path: { session_id: sessionId } },
          body,
        }),
      ),
  });
}
