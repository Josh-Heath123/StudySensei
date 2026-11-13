import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { routes } from "@/app/routes";
import { SessionProvider } from "@/features/session/SessionProvider";

/**
 * Render the real app routes at a path, with a fresh query cache and session
 * controller (a new page load; localStorage carries over unless cleared).
 */
export function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <RouterProvider router={router} />
      </SessionProvider>
    </QueryClientProvider>,
  );
  return { ...view, router };
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
 * (healthy by default), /sessions/active gets null (no open session) and every other GET
 * gets an empty list. Returns the fetch mock.
 */
export function stubHealth(
  health: () => Promise<Response> | Response = () => jsonResponse(HEALTHY),
) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith("/health")) return health();
    if (path.endsWith("/sessions/active")) return jsonResponse(null);
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
