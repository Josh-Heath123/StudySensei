import { screen } from "@testing-library/react";
import { vi } from "vitest";

import { jsonResponse, renderApp } from "@/test/render";

test("shows API and database connected", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ status: "ok", api: "ok", database: "ok" })),
  );
  renderApp();

  expect(await screen.findByLabelText("API: Connected")).toBeInTheDocument();
  expect(screen.getByLabelText("Database: Connected")).toBeInTheDocument();
});

test("shows database error when /health returns 503", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse(
        {
          status: "degraded",
          api: "ok",
          database: "error",
          database_error: "ConnectionRefusedError",
        },
        503,
      ),
    ),
  );
  renderApp();

  expect(await screen.findByLabelText("Database: Not connected")).toBeInTheDocument();
  expect(screen.getByLabelText("API: Connected")).toBeInTheDocument();
  expect(screen.getByText(/ConnectionRefusedError/)).toBeInTheDocument();
});

test("shows API unreachable when the request fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }),
  );
  renderApp();

  expect(await screen.findByLabelText("API: Not connected")).toBeInTheDocument();
  expect(screen.getByLabelText("Database: Unknown")).toBeInTheDocument();
});

test("treats a dev-proxy error (API stopped) as API unreachable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("Error occurred while trying to proxy", { status: 502 })),
  );
  renderApp();

  expect(await screen.findByLabelText("API: Not connected")).toBeInTheDocument();
  expect(screen.getByLabelText("Database: Unknown")).toBeInTheDocument();
});

test("calls the API on the page's own origin under /api", async () => {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () =>
    jsonResponse({ status: "ok", api: "ok", database: "ok" }),
  );
  vi.stubGlobal("fetch", fetchMock);
  renderApp();

  await screen.findByLabelText("API: Connected");
  expect(fetchMock.mock.calls[0]![0].url).toBe(`${window.location.origin}/api/health`);
});
