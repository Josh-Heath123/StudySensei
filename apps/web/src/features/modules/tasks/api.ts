import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Task = components["schemas"]["TaskOut"];
export type TaskInput = components["schemas"]["TaskCreate"];
export type TaskChanges = components["schemas"]["TaskUpdate"];
export type TaskStatus = Task["status"];

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
};

const tasksKey = (moduleId: string) => ["tasks", moduleId] as const;

export function useTasks(moduleId: string) {
  return useQuery({
    queryKey: tasksKey(moduleId),
    queryFn: () => unwrap(api.GET("/tasks", { params: { query: { module_id: moduleId } } })),
  });
}

function useTaskMutation<TArgs>(moduleId: string, mutationFn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: tasksKey(moduleId) }),
  });
}

export function useCreateTask(moduleId: string) {
  return useTaskMutation(moduleId, (body: TaskInput) =>
    unwrap(
      api.POST("/modules/{module_id}/tasks", { params: { path: { module_id: moduleId } }, body }),
    ),
  );
}

export function useUpdateTask(moduleId: string) {
  return useTaskMutation(moduleId, (args: { id: string; changes: TaskChanges }) =>
    unwrap(
      api.PATCH("/tasks/{task_id}", { params: { path: { task_id: args.id } }, body: args.changes }),
    ),
  );
}

export function useDeleteTask(moduleId: string) {
  return useTaskMutation(moduleId, (id: string) =>
    unwrap(api.DELETE("/tasks/{task_id}", { params: { path: { task_id: id } } })),
  );
}
