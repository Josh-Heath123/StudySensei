import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Plan = components["schemas"]["PlanOut"];
export type PlanBlock = components["schemas"]["StoredBlockOut"];
export type PlanVersion = components["schemas"]["PlanVersionOut"];

export const planKeys = {
  all: ["plan"] as const,
  range: (from: string, to: string) => ["plan", "range", from, to] as const,
  next: ["plan", "next"] as const,
};

/**
 * GET /plan for local dates `from` to `to`. `poll` says how often to refetch, given the
 * latest plan (the page polls while a re-plan is pending).
 */
export function usePlan(
  from: string | null,
  to: string | null,
  poll: (plan: Plan | undefined) => number | false = () => false,
) {
  return useQuery({
    queryKey: planKeys.range(from ?? "", to ?? ""),
    queryFn: () => unwrap(api.GET("/plan", { params: { query: { from: from!, to: to! } } })),
    enabled: from !== null && to !== null,
    refetchInterval: (query) => poll(query.state.data),
  });
}

/** GET /plan/next: the next planned block with its actions, or null. */
export function useNextBlock() {
  return useQuery({
    queryKey: planKeys.next,
    queryFn: () => unwrap(api.GET("/plan/next")),
  });
}

function usePlanMutation<TArgs, TResult>(mutationFn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: planKeys.all }),
  });
}

export function useSkipBlock() {
  return usePlanMutation((blockId: string) =>
    unwrap(api.POST("/plan/blocks/{block_id}/skip", { params: { path: { block_id: blockId } } })),
  );
}

/** Move a block; the server checks the move and answers 422 with one sentence if it can't. */
export function useMoveBlock() {
  return usePlanMutation(({ blockId, start }: { blockId: string; start: string }) =>
    unwrap(
      api.POST("/plan/blocks/{block_id}/move", {
        params: { path: { block_id: blockId } },
        body: { start },
      }),
    ),
  );
}
