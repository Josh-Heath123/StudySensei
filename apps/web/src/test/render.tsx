import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { routes } from "@/app/routes";

/** Render the real app routes at a path, with a fresh query cache. */
export function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const HEALTHY = { status: "ok", api: "ok", database: "ok" };

/**
 * Stub fetch for pages that only need the status card to work: /health gets `health()`
 * (healthy by default) and every other GET gets an empty list. Returns the fetch mock.
 */
export function stubHealth(
  health: () => Promise<Response> | Response = () => jsonResponse(HEALTHY),
) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async (request) =>
    new URL(request.url).pathname.endsWith("/health") ? health() : jsonResponse([]),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
