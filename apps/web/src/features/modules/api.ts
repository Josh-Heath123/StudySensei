import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Module = components["schemas"]["ModuleOut"];
export type ModuleInput = components["schemas"]["ModuleCreate"];
export type ModuleChanges = components["schemas"]["ModuleUpdate"];
export type TopicNode = components["schemas"]["TopicNodeOut"];
export type TopicMove = components["schemas"]["TopicMove"];

export const keys = {
  modules: ["modules"] as const,
  module: (id: string) => ["modules", id] as const,
  topics: (moduleId: string) => ["topics", moduleId] as const,
};

// --- Modules -----------------------------------------------------------------------

export function useModules() {
  return useQuery({
    queryKey: keys.modules,
    queryFn: () => unwrap(api.GET("/modules")),
  });
}

export function useModule(moduleId: string) {
  return useQuery({
    queryKey: keys.module(moduleId),
    queryFn: () =>
      unwrap(api.GET("/modules/{module_id}", { params: { path: { module_id: moduleId } } })),
  });
}

export function useCreateModule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ModuleInput) => unwrap(api.POST("/modules", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.modules }),
  });
}

export function useUpdateModule(moduleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ModuleChanges) =>
      unwrap(
        api.PATCH("/modules/{module_id}", { params: { path: { module_id: moduleId } }, body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.modules }),
  });
}

export function useDeleteModule(moduleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE("/modules/{module_id}", { params: { path: { module_id: moduleId } } })),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.module(moduleId) });
      queryClient.removeQueries({ queryKey: keys.topics(moduleId) });
      return queryClient.invalidateQueries({ queryKey: keys.modules });
    },
  });
}

// --- Topics ------------------------------------------------------------------------

export function useTopicTree(moduleId: string) {
  return useQuery({
    queryKey: keys.topics(moduleId),
    queryFn: () =>
      unwrap(api.GET("/modules/{module_id}/topics", { params: { path: { module_id: moduleId } } })),
  });
}

/** All topic mutations refresh the module's tree when they finish. */
function useTopicMutation<TArgs>(moduleId: string, mutationFn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.topics(moduleId) }),
  });
}

export function useCreateTopic(moduleId: string) {
  return useTopicMutation(moduleId, (args: { name: string; parentId: string | null }) =>
    unwrap(
      api.POST("/modules/{module_id}/topics", {
        params: { path: { module_id: moduleId } },
        body: { name: args.name, parent_id: args.parentId },
      }),
    ),
  );
}

export function useRenameTopic(moduleId: string) {
  return useTopicMutation(moduleId, (args: { topicId: string; name: string }) =>
    unwrap(
      api.PATCH("/topics/{topic_id}", {
        params: { path: { topic_id: args.topicId } },
        body: { name: args.name },
      }),
    ),
  );
}

export function useMoveTopic(moduleId: string) {
  return useTopicMutation(moduleId, (args: { topicId: string } & TopicMove) =>
    unwrap(
      api.POST("/topics/{topic_id}/move", {
        params: { path: { topic_id: args.topicId } },
        body: { parent_id: args.parent_id, position: args.position },
      }),
    ),
  );
}

export function useDeleteTopic(moduleId: string) {
  return useTopicMutation(moduleId, (topicId: string) =>
    unwrap(api.DELETE("/topics/{topic_id}", { params: { path: { topic_id: topicId } } })),
  );
}

// --- Topic map (decision 0006) -------------------------------------------------------

export type TopicMapStatus = components["schemas"]["TopicMapStatus"];
export type AiStatus = components["schemas"]["AIStatusOut"];

const TOPIC_MAP_POLL_MS = 3000;

/** Busy while materials are being analysed or merged; polled until it isn't. */
export const topicMapBusy = (s: TopicMapStatus | undefined) =>
  s !== undefined && (s.pending > 0 || s.merging);

export function useTopicMap(moduleId: string) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ["topic-map", moduleId],
    queryFn: async () => {
      const previous = queryClient.getQueryData<TopicMapStatus>(["topic-map", moduleId]);
      const status = await unwrap(
        api.GET("/modules/{module_id}/topic-map", { params: { path: { module_id: moduleId } } }),
      );
      // New topics and page links appear as jobs finish: refresh the tree while it's busy.
      if (topicMapBusy(previous)) {
        void queryClient.invalidateQueries({ queryKey: keys.topics(moduleId) });
      }
      return status;
    },
    refetchInterval: (query) => (topicMapBusy(query.state.data) ? TOPIC_MAP_POLL_MS : false),
  });
}

export function useBuildTopicMap(moduleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/modules/{module_id}/topic-map/build", {
          params: { path: { module_id: moduleId } },
        }),
      ),
    onSuccess: (status) => queryClient.setQueryData(["topic-map", moduleId], status),
  });
}

export function useAiStatus() {
  return useQuery({
    queryKey: ["ai-status"],
    queryFn: () => unwrap(api.GET("/ai/status")),
    staleTime: 60_000,
  });
}

/** Delete every topic still marked AI (the student's own and edited ones stay). */
export function useClearAiTopics(moduleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/modules/{module_id}/ai-topics", {
          params: { path: { module_id: moduleId } },
        }),
      ),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.topics(moduleId) }),
        queryClient.invalidateQueries({ queryKey: ["topic-map", moduleId] }),
      ]),
  });
}
