import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/**
 * Typed client generated from the API's OpenAPI schema (`npm run gen:api`).
 * fetch is looked up on each call so tests can stub it.
 */
export const api = createClient<paths>({
  baseUrl: API_URL,
  fetch: (request) => globalThis.fetch(request),
});
