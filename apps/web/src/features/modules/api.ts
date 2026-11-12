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
