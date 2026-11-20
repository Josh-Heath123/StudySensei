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

/**
 * Any change to study time: everything under it is refetched (the week total too), and the
 * plan, which the change re-plans (decision 0021).
 */
function useStudyTimeMutation<TArgs>(mutationFn: (args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: studyTimeKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["plan"] }),
      ]),
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

export function useUpdateException() {
  return useStudyTimeMutation(
    ({ id, ...body }: { id: string } & components["schemas"]["ExceptionUpdate"]) =>
      unwrap(
        api.PATCH("/availability/exceptions/{exception_id}", {
          params: { path: { exception_id: id } },
          body,
        }),
      ),
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

// --- Reminders and the calendar feed (decision 0024) ------------------------------

export type PushDevice = components["schemas"]["PushSubscriptionOut"];
export type PushTestResult = components["schemas"]["PushTestOut"];
export type CalendarFeed = components["schemas"]["CalendarFeedOut"];

export const reminderKeys = {
  config: ["push", "config"] as const,
  devices: ["push", "devices"] as const,
  feed: ["calendar", "feed"] as const,
};

export function usePushConfig() {
  return useQuery({
    queryKey: reminderKeys.config,
    queryFn: () => unwrap(api.GET("/push/config")),
  });
}

export function usePushDevices(enabled = true) {
  return useQuery({
    queryKey: reminderKeys.devices,
    queryFn: () => unwrap(api.GET("/push/subscriptions")),
    enabled,
  });
}

function useDevicesMutation<TArgs, TResult>(mutationFn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: reminderKeys.devices }),
  });
}

/** Save this device's subscription (the server upserts it by endpoint). */
export function useSaveDevice() {
  return useDevicesMutation((body: components["schemas"]["PushSubscriptionIn"]) =>
    unwrap(api.POST("/push/subscriptions", { body })),
  );
}

export function useRemoveDevice() {
  return useDevicesMutation((id: string) =>
    unwrap(
      api.DELETE("/push/subscriptions/{subscription_id}", {
        params: { path: { subscription_id: id } },
      }),
    ),
  );
}

/** POST /push/test: "Reminders work" to each device, with each one's outcome. */
export function useTestPush() {
  return useDevicesMutation(() => unwrap(api.POST("/push/test")));
}

/** The lead time only: it doesn't change the plan, so nothing else is refetched. */
export function useSetReminderMinutes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (minutes: PlanningSettings["reminder_minutes"]) =>
      unwrap(api.PATCH("/planning/settings", { body: { reminder_minutes: minutes } })),
    onSuccess: (settings) => queryClient.setQueryData(studyTimeKeys.settings, settings),
  });
}

export function useCalendarFeed() {
  return useQuery({
    queryKey: reminderKeys.feed,
    queryFn: () => unwrap(api.GET("/calendar/feed")),
  });
}

function useFeedMutation<TArgs, TResult>(mutationFn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: reminderKeys.feed }),
  });
}

/** Create or reset the private link; the URL comes back this once. */
export function useCreateFeed() {
  return useFeedMutation(() => unwrap(api.POST("/calendar/feed")));
}

export function useDeleteFeed() {
  return useFeedMutation(() => unwrap(api.DELETE("/calendar/feed")));
}
