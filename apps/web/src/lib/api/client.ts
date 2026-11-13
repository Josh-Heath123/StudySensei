import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];

/**
 * Where the API lives. By default it's `/api` on the page's own origin: in
 * development Vite proxies `/api/*` to the API on :8000 (see vite.config.ts),
 * so the browser never makes a cross-origin request. Set VITE_API_URL to call
 * an API directly instead (the API keeps CORS enabled for that).
 */
export const API_URL: string = new URL(
  import.meta.env.VITE_API_URL ?? "/api",
  window.location.origin,
).href.replace(/\/$/, "");

/**
 * Typed client generated from the API's OpenAPI schema (`npm run gen:api`).
 * fetch is looked up on each call so tests can stub it.
 */
export const api = createClient<paths>({
  baseUrl: API_URL,
  fetch: (request) => globalThis.fetch(request),
});
