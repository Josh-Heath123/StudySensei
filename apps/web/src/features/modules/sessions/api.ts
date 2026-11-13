import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type SessionRow = components["schemas"]["SessionOut"];
export type SessionPage = components["schemas"]["SessionPage"];
export type SessionSummary = components["schemas"]["ModuleSessionSummary"];

export const PAGE_SIZE = 20;

export const sessionKeys = {
  all: ["sessions"] as const,
  list: (moduleId: string) => ["sessions", "module", moduleId] as const,
  summary: (moduleId: string, weekStart: string) =>
    ["sessions", "module", moduleId, "summary", weekStart] as const,
  detail: (sessionId: string) => ["sessions", "detail", sessionId] as const,
};

/** The module's sessions, a page at a time (the open one first, then newest first). */
export function useModuleSessions(moduleId: string) {
  return useInfiniteQuery({
    queryKey: sessionKeys.list(moduleId),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/modules/{module_id}/sessions", {
          params: {
            path: { module_id: moduleId },
            query: { limit: PAGE_SIZE, offset: pageParam },
          },
        }),
      ),
    getNextPageParam: (last: SessionPage) =>
      last.offset + last.items.length < last.total ? last.offset + last.items.length : undefined,
  });
}

/** Measured study time for the module: this week (from `weekStart`) and all time. */
export function useSessionSummary(moduleId: string, weekStart: Date) {
  const week = weekStart.toISOString();
  return useQuery({
    queryKey: sessionKeys.summary(moduleId, week),
    queryFn: () =>
      unwrap(
        api.GET("/modules/{module_id}/sessions/summary", {
          params: { path: { module_id: moduleId }, query: { week_start: week } },
        }),
      ),
  });
}

/** One session with its events (for the timeline). */
export function useSessionDetail(sessionId: string) {
  return useQuery({
    queryKey: sessionKeys.detail(sessionId),
    queryFn: () =>
      unwrap(api.GET("/sessions/{session_id}", { params: { path: { session_id: sessionId } } })),
  });
}
