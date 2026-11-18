import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export { useAiStatus } from "@/features/modules/api";

export type AiStatus = components["schemas"]["AIStatusOut"];
export type AiModelStatus = components["schemas"]["AIModelStatus"];
export type AiPingResult = components["schemas"]["AIPingResult"];

/** POST /ai/ping: one request per configured model, then the usage on /ai/status is stale. */
export function usePingModels() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/ai/ping")),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["ai-status"] }),
  });
}
