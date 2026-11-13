import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

import { taskKeys } from "./keys";

export type Task = components["schemas"]["TaskOut"];
export type TaskInput = components["schemas"]["TaskCreate"];
export type TaskChanges = components["schemas"]["TaskUpdate"];
export type TaskStatus = Task["status"];

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
};

export function useTasks(moduleId: string) {
  return useQuery({
    queryKey: taskKeys.forModule(moduleId),
    queryFn: () =>
      unwrap(api.GET("/modules/{module_id}/tasks", { params: { path: { module_id: moduleId } } })),
  });
}

function useTaskMutation<TArgs>(mutationFn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    // Every task list: this module's and Today's.
    onSettled: () => queryClient.invalidateQueries({ queryKey: taskKeys.all }),
  });
}

export function useCreateTask(moduleId: string) {
  return useTaskMutation((body: TaskInput) =>
    unwrap(
      api.POST("/modules/{module_id}/tasks", { params: { path: { module_id: moduleId } }, body }),
    ),
  );
}

export function useUpdateTask() {
  return useTaskMutation((args: { id: string; changes: TaskChanges }) =>
    unwrap(
      api.PATCH("/tasks/{task_id}", { params: { path: { task_id: args.id } }, body: args.changes }),
    ),
  );
}

export function useDeleteTask() {
  return useTaskMutation((id: string) =>
    unwrap(api.DELETE("/tasks/{task_id}", { params: { path: { task_id: id } } })),
  );
}
