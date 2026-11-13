import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";

import { assessmentKeys } from "../modules/assessments/api";
import { taskKeys } from "../modules/tasks/keys";

/** Upcoming assessments across all modules. Under the "assessments" prefix, so module
 *  mutations refresh it. */
export function useUpcomingAssessments() {
  return useQuery({
    queryKey: [...assessmentKeys.all, "upcoming"],
    queryFn: () => unwrap(api.GET("/assessments", { params: { query: { status: ["upcoming"] } } })),
  });
}

/** Unfinished tasks across all modules. */
export function useOpenTasks() {
  return useQuery({
    queryKey: [...taskKeys.all, "open"],
    queryFn: () =>
      unwrap(api.GET("/tasks", { params: { query: { status: ["todo", "in_progress"] } } })),
  });
}
