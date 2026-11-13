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
