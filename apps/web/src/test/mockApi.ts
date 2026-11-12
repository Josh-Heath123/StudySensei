import { vi } from "vitest";

export type ApiCall = { method: string; path: string; body: unknown };

type Reply = unknown | Response;
type Handler = (call: ApiCall & { params: Record<string, string> }) => Reply | Promise<Reply>;

/**
 * Stub fetch with a tiny router: keys look like "GET /modules/:moduleId".
 * Handlers return a body (sent as 200 JSON) or a Response for other statuses.
 * Every request is recorded in `calls`; an unmatched request fails the test.
 */
export function mockApi(routes: Record<string, Handler>) {
  const calls: ApiCall[] = [];
  const table = Object.entries(routes).map(([key, handler]) => {
    const [method, pattern] = key.split(" ") as [string, string];
    const names: string[] = [];
    const regex = new RegExp(
      "^" + pattern.replace(/:(\w+)/g, (_, name: string) => (names.push(name), "([^/]+)")) + "$",
    );
    return { method, regex, names, handler };
  });

  const fetchMock = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    const text = await request.text();
    const call: ApiCall = { method: request.method, path, body: text ? JSON.parse(text) : null };
    calls.push(call);

    for (const route of table) {
      const match = route.method === call.method && route.regex.exec(path);
      if (match) {
        const params = Object.fromEntries(route.names.map((name, i) => [name, match[i + 1]!]));
        const reply = await route.handler({ ...call, params });
        return reply instanceof Response ? reply : json(reply ?? null);
      }
    }
    throw new Error(`mockApi: no route for ${call.method} ${path}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function json(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const noContent = () => new Response(null, { status: 204 });
