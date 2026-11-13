import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

import { taskKeys } from "../tasks/keys";

export type Assessment = components["schemas"]["AssessmentOut"];
export type AssessmentInput = components["schemas"]["AssessmentCreate"];
export type AssessmentChanges = components["schemas"]["AssessmentUpdate"];
export type AssessmentKind = Assessment["kind"];
export type AssessmentStatus = Assessment["status"];

export const assessmentKeys = {
  all: ["assessments"] as const,
  forModule: (moduleId: string) => ["assessments", "module", moduleId] as const,
};

export const KIND_LABELS: Record<AssessmentKind, string> = {
  exam: "Exam",
  test: "Test",
  assignment: "Assignment",
  quiz: "Quiz",
  project: "Project",
  other: "Other",
};

export const STATUS_LABELS: Record<AssessmentStatus, string> = {
  upcoming: "Upcoming",
  completed: "Completed",
  cancelled: "Cancelled",
};

/** Sensible default time of day per kind: sit-down assessments start in the morning,
 *  hand-ins are due at the end of the day. */
export const DEFAULT_TIME: Record<AssessmentKind, string> = {
  exam: "09:00",
  test: "09:00",
  quiz: "09:00",
  assignment: "23:59",
  project: "23:59",
  other: "09:00",
};

export function useAssessments(moduleId: string) {
  return useQuery({
    queryKey: assessmentKeys.forModule(moduleId),
    queryFn: () =>
      unwrap(
        api.GET("/modules/{module_id}/assessments", { params: { path: { module_id: moduleId } } }),
      ),
  });
}

function useAssessmentMutation<TArgs>(mutationFn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    // Every assessment list (this module's and Today's), and tasks: they show their
    // assessment's title, and deleting one unlinks its tasks.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: assessmentKeys.all }),
        queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      ]),
  });
}

export function useCreateAssessment(moduleId: string) {
  return useAssessmentMutation((body: AssessmentInput) =>
    unwrap(
      api.POST("/modules/{module_id}/assessments", {
        params: { path: { module_id: moduleId } },
        body,
      }),
    ),
  );
}

export function useUpdateAssessment() {
  return useAssessmentMutation((args: { id: string; changes: AssessmentChanges }) =>
    unwrap(
      api.PATCH("/assessments/{assessment_id}", {
        params: { path: { assessment_id: args.id } },
        body: args.changes,
      }),
    ),
  );
}

export function useDeleteAssessment() {
  return useAssessmentMutation((id: string) =>
    unwrap(api.DELETE("/assessments/{assessment_id}", { params: { path: { assessment_id: id } } })),
  );
}
