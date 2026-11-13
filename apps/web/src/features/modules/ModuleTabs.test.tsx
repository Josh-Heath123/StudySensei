import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule } from "./fixtures";

function api() {
  return mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => [],
    "GET /modules/:id/assessments": () => [],
    "GET /modules/:id/tasks": () => [],
    "GET /sessions/active": () => null,
    "GET /modules/:id/sessions": () => ({ items: [], total: 0, limit: 20, offset: 0 }),
    "GET /modules/:id/sessions/summary": () => ({
      session_count: 0,
      active_seconds: 0,
      week_start: "2026-11-09T00:00:00Z",
      week_active_seconds: 0,
    }),
  });
}

test("opens on Assessments and switches tabs", async () => {
  api();
  renderApp("/modules/m1");
  const user = userEvent.setup();

  expect(await screen.findByRole("tab", { name: "Assessments" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(await screen.findByRole("heading", { name: "Assessments" })).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Tasks" }));
  expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Topics" }));
  expect(await screen.findByRole("heading", { name: "Topics" })).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Sessions" }));
  expect(await screen.findByRole("heading", { name: "Sessions" })).toBeInTheDocument();
});

test("?tab= opens that tab directly", async () => {
  api();
  renderApp("/modules/m1?tab=topics");
  expect(await screen.findByRole("tab", { name: "Topics" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("an unknown ?tab= falls back to Assessments", async () => {
  api();
  renderApp("/modules/m1?tab=nonsense");
  expect(await screen.findByRole("tab", { name: "Assessments" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});
