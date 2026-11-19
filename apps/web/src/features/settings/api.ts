import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export { useAiStatus } from "@/features/modules/api";

export type AiStatus = components["schemas"]["AIStatusOut"];
export type AiModelStatus = components["schemas"]["AIModelStatus"];
export type AiPingResult = components["schemas"]["AIPingResult"];

// --- Study time (planning) -------------------------------------------------------

export type PlanningSettings = components["schemas"]["PlanningSettingsOut"];
export type Rule = components["schemas"]["RuleOut"];
export type AvailabilityException = components["schemas"]["ExceptionOut"];
export type ExceptionInput = components["schemas"]["ExceptionCreate"];
export type Availability = components["schemas"]["AvailabilityOut"];

const studyTime = ["study-time"] as const;
export const studyTimeKeys = {
  all: studyTime,
  settings: [...studyTime, "settings"] as const,
  rules: [...studyTime, "rules"] as const,
  exceptions: (from: string) => [...studyTime, "exceptions", from] as const,
  availability: (from: string, to: string) => [...studyTime, "availability", from, to] as const,
};

export function usePlanningSettings() {
  return useQuery({
    queryKey: studyTimeKeys.settings,
    queryFn: () => unwrap(api.GET("/planning/settings")),
  });
}

export function useRules() {
  return useQuery({
    queryKey: studyTimeKeys.rules,
    queryFn: () => unwrap(api.GET("/availability/rules")),
  });
}

/** Exceptions from `from` (a local date) on. */
export function useExceptions(from: string | null) {
  return useQuery({
    queryKey: studyTimeKeys.exceptions(from ?? ""),
    queryFn: () =>
      unwrap(api.GET("/availability/exceptions", { params: { query: { from: from! } } })),
    enabled: from !== null,
  });
}

/** Free time per local date from `from` to `to` (inclusive), after exceptions and the cap. */
export function useAvailability(from: string | null, to: string | null) {
  return useQuery({
    queryKey: studyTimeKeys.availability(from ?? "", to ?? ""),
    queryFn: () =>
      unwrap(api.GET("/availability", { params: { query: { from: from!, to: to! } } })),
    enabled: from !== null && to !== null,
  });
}

/** Any change to study time: everything under it is refetched (the week total too). */
function useStudyTimeMutation<TArgs>(mutationFn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: studyTimeKeys.all }),
  });
}

export function useUpdatePlanningSettings() {
  return useStudyTimeMutation((body: components["schemas"]["PlanningSettingsUpdate"]) =>
    unwrap(api.PATCH("/planning/settings", { body })),
  );
}

export function useCreateRule() {
  return useStudyTimeMutation((body: components["schemas"]["RuleCreate"]) =>
    unwrap(api.POST("/availability/rules", { body })),
  );
}

export function useUpdateRule() {
  return useStudyTimeMutation(
    ({ id, ...body }: { id: string } & components["schemas"]["RuleUpdate"]) =>
      unwrap(
        api.PATCH("/availability/rules/{rule_id}", { params: { path: { rule_id: id } }, body }),
      ),
  );
}

export function useDeleteRule() {
  return useStudyTimeMutation((id: string) =>
    unwrap(api.DELETE("/availability/rules/{rule_id}", { params: { path: { rule_id: id } } })),
  );
}

export function useCreateException() {
  return useStudyTimeMutation((body: ExceptionInput) =>
    unwrap(api.POST("/availability/exceptions", { body })),
  );
}

export function useDeleteException() {
  return useStudyTimeMutation((id: string) =>
    unwrap(
      api.DELETE("/availability/exceptions/{exception_id}", {
        params: { path: { exception_id: id } },
      }),
    ),
  );
}

/** POST /ai/ping: one request per configured model, then the usage on /ai/status is stale. */
export function usePingModels() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/ai/ping")),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["ai-status"] }),
  });
}
