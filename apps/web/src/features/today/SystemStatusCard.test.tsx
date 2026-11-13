import { screen } from "@testing-library/react";
import { jsonResponse, renderApp, stubHealth } from "@/test/render";

test("shows API and database connected", async () => {
  stubHealth();
  renderApp();

  expect(await screen.findByLabelText("API: Connected")).toBeInTheDocument();
  expect(screen.getByLabelText("Database: Connected")).toBeInTheDocument();
});

test("shows database error when /health returns 503", async () => {
  stubHealth(() =>
    jsonResponse(
      {
        status: "degraded",
        api: "ok",
        database: "error",
        database_error: "ConnectionRefusedError",
      },
      503,
    ),
  );
  renderApp();

  expect(await screen.findByLabelText("Database: Not connected")).toBeInTheDocument();
  expect(screen.getByLabelText("API: Connected")).toBeInTheDocument();
  expect(screen.getByText(/ConnectionRefusedError/)).toBeInTheDocument();
});

test("shows API unreachable when the request fails", async () => {
  stubHealth(() => {
    throw new TypeError("Failed to fetch");
  });
  renderApp();

  expect(await screen.findByLabelText("API: Not connected")).toBeInTheDocument();
  expect(screen.getByLabelText("Database: Unknown")).toBeInTheDocument();
});

test("treats a dev-proxy error (API stopped) as API unreachable", async () => {
  stubHealth(() => new Response("Error occurred while trying to proxy", { status: 502 }));
  renderApp();

  expect(await screen.findByLabelText("API: Not connected")).toBeInTheDocument();
  expect(screen.getByLabelText("Database: Unknown")).toBeInTheDocument();
});

test("calls the API on the page's own origin under /api", async () => {
  const fetchMock = stubHealth();
  renderApp();

  await screen.findByLabelText("API: Connected");
  const urls = fetchMock.mock.calls.map(([request]) => request.url);
  expect(urls).toContain(`${window.location.origin}/api/health`);
  expect(urls.every((url) => url.startsWith(`${window.location.origin}/api/`))).toBe(true);
});
