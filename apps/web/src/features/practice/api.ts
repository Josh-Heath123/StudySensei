import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { keys as moduleKeys } from "@/features/modules/api";
import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type PracticeItem = components["schemas"]["ItemOut"];
export type ItemInput = components["schemas"]["ItemCreate"];
export type ItemChanges = components["schemas"]["ItemUpdate"];
export type ItemKind = PracticeItem["kind"];
export type ItemStatus = PracticeItem["status"];
export type ItemOrigin = PracticeItem["origin"];
export type RejectReason = NonNullable<ItemChanges["reject_reason"]>;
export type QueueCounts = components["schemas"]["QueueCounts"];
export type Queue = components["schemas"]["QueueOut"];
export type Preview = components["schemas"]["PreviewOut"];
export type ReviewInput = components["schemas"]["ReviewIn"];
export type ReviewResult = components["schemas"]["ReviewResultOut"];
export type AiMarking = components["schemas"]["AIMarking"];
export type Generation = components["schemas"]["GenerationOut"];
export type PracticeSettings = components["schemas"]["PracticeSettingsOut"];
export type ModuleMastery = components["schemas"]["ModuleMasteryOut"];

export type ItemFilters = {
  moduleId?: string;
  topicId?: string;
  status?: ItemStatus;
  origin?: ItemOrigin;
  kind?: ItemKind;
};

/** Everything practice lives under "practice", so a review refreshes all of it at once. */
export const practiceKeys = {
  all: ["practice"] as const,
  queue: (moduleId?: string) => ["practice", "queue", moduleId ?? "all"] as const,
  items: (filters: ItemFilters) => ["practice", "items", filters] as const,
  preview: (itemId: string) => ["practice", "preview", itemId] as const,
  generations: (topicId: string) => ["practice", "generations", topicId] as const,
  settings: ["practice", "settings"] as const,
};

/** Mastery sits under the module's topic key (as in the topic dialog), so a review, a
 * rating or a new card refreshes it. */
const masteryKey = (moduleId: string) => [...moduleKeys.topics(moduleId), "mastery"] as const;

/** After anything that changes items or reviews: the queue, lists, previews and mastery. */
function useRefreshPractice() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: practiceKeys.all }),
      queryClient.invalidateQueries({ queryKey: ["topics"] }),
    ]);
}

// --- The queue and reviewing ---------------------------------------------------------

export function useQueue(moduleId?: string, refetchInterval?: number | false) {
  return useQuery({
    queryKey: practiceKeys.queue(moduleId),
    queryFn: () =>
      unwrap(
        api.GET("/practice/queue", {
          params: { query: { module_id: moduleId, limit: 20 } },
        }),
      ),
    refetchInterval,
  });
}

export function usePreview(itemId: string | undefined) {
  return useQuery({
    queryKey: practiceKeys.preview(itemId ?? ""),
    enabled: itemId !== undefined,
    queryFn: () =>
      unwrap(
        api.GET("/practice/items/{item_id}/preview", {
          params: { path: { item_id: itemId! } },
        }),
      ),
  });
}

export function useReview() {
  const refresh = useRefreshPractice();
  return useMutation({
    mutationFn: ({ itemId, ...body }: { itemId: string } & ReviewInput) =>
      unwrap(
        api.POST("/practice/items/{item_id}/reviews", {
          params: { path: { item_id: itemId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
}

/** Ask the AI to check a short answer (ADR 0029). Stores nothing. */
export function useMarkAnswer() {
  return useMutation({
    mutationFn: ({ itemId, answer }: { itemId: string; answer: string }) =>
      unwrap(
        api.POST("/practice/items/{item_id}/mark", {
          params: { path: { item_id: itemId } },
          body: { answer_text: answer },
        }),
      ),
  });
}

// --- Items ---------------------------------------------------------------------------

export function useItems(filters: ItemFilters, enabled = true) {
  return useQuery({
    queryKey: practiceKeys.items(filters),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/practice/items", {
          params: {
            query: {
              module_id: filters.moduleId,
              topic_id: filters.topicId,
              status: filters.status,
              origin: filters.origin,
              kind: filters.kind,
              // A topic covers its subtopics, as its mastery and counts do.
              subtopics: filters.topicId ? true : undefined,
              limit: 200,
            },
          },
        }),
      ),
  });
}

export function useCreateItem() {
  const refresh = useRefreshPractice();
  return useMutation({
    mutationFn: (body: ItemInput) => unwrap(api.POST("/practice/items", { body })),
    onSuccess: refresh,
  });
}

export function useUpdateItem() {
  const refresh = useRefreshPractice();
  return useMutation({
    mutationFn: ({ itemId, ...body }: { itemId: string } & ItemChanges) =>
      unwrap(
        api.PATCH("/practice/items/{item_id}", { params: { path: { item_id: itemId } }, body }),
      ),
    onSuccess: refresh,
  });
}

export function useDeleteItem() {
  const refresh = useRefreshPractice();
  return useMutation({
    mutationFn: (itemId: string) =>
      unwrap(api.DELETE("/practice/items/{item_id}", { params: { path: { item_id: itemId } } })),
    onSuccess: refresh,
  });
}

// --- Generation ----------------------------------------------------------------------

/** The topic's recent generations; polled every 2 s while the newest is queued or running.
 * Off until asked for (a page of topics would otherwise ask once per topic). */
export function useGenerations(topicId: string, enabled = true) {
  return useQuery({
    queryKey: practiceKeys.generations(topicId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/topics/{topic_id}/practice/generations", {
          params: { path: { topic_id: topicId } },
        }),
      ),
    refetchInterval: (query) => {
      const newest = query.state.data?.[0];
      return newest && (newest.status === "queued" || newest.status === "running") ? 2_000 : false;
    },
  });
}

export function useGenerate(topicId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/topics/{topic_id}/practice/generate", {
          params: { path: { topic_id: topicId } },
          body: { count: 8 },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: practiceKeys.generations(topicId) }),
  });
}

// --- Mastery and settings ------------------------------------------------------------

/** Every topic's mastery, for each module asked for (ADR 0027). */
export function useModulesMastery(moduleIds: string[]) {
  return useQueries({
    queries: moduleIds.map((moduleId) => ({
      queryKey: masteryKey(moduleId),
      queryFn: () =>
        unwrap(
          api.GET("/modules/{module_id}/mastery", {
            params: { path: { module_id: moduleId } },
          }),
        ),
    })),
  });
}

export function usePracticeSettings() {
  return useQuery({
    queryKey: practiceKeys.settings,
    queryFn: () => unwrap(api.GET("/practice/settings")),
  });
}

export function useUpdatePracticeSettings() {
  const refresh = useRefreshPractice();
  return useMutation({
    mutationFn: (body: components["schemas"]["PracticeSettingsUpdate"]) =>
      unwrap(api.PATCH("/practice/settings", { body })),
    onSuccess: refresh,
  });
}
