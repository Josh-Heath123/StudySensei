import { useQuery } from "@tanstack/react-query";

import { api, type HealthResponse } from "@/lib/api/client";

/**
 * Polls GET /health. A 503 still has a body (database down, API up),
 * so it resolves with data. Only a network failure becomes an error,
 * which means the API itself is unreachable.
 */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async (): Promise<HealthResponse> => {
      const { data, error } = await api.GET("/health");
      const body = data ?? error;
      if (!body) throw new Error("Empty /health response");
      return body;
    },
    refetchInterval: 10_000,
    retry: false,
  });
}
