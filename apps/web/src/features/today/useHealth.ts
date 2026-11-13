import { useQuery } from "@tanstack/react-query";

import { api, type HealthResponse } from "@/lib/api/client";

/**
 * Polls GET /health.
 * - 200: everything is up.
 * - 503 with the API's own body (`api: "ok"`): the API is up, the database isn't.
 * - Anything else (network error, or the dev proxy's 500/502 when the API is
 *   stopped) means the API itself is unreachable, so the query errors.
 */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async (): Promise<HealthResponse> => {
      const { data, error, response } = await api.GET("/health");
      if (response.ok && data) return data;
      if (response.status === 503 && error?.api === "ok") return error;
      throw new Error(`API unreachable (HTTP ${response.status})`);
    },
    refetchInterval: 10_000,
    retry: false,
  });
}
