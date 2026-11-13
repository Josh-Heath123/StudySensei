import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp, stubHealth } from "@/test/render";

beforeEach(() => {
  stubHealth();
});

test("the top navigation links to all six sections", () => {
  renderApp();
  const nav = screen.getByRole("navigation", { name: "Main" });
  for (const label of ["Today", "Modules", "Plan", "Practice", "Insights", "Settings"]) {
    expect(nav).toContainElement(screen.getByRole("link", { name: label }));
  }
});

test("clicking a link shows that page", async () => {
  renderApp();
  await userEvent.click(screen.getByRole("link", { name: "Plan" }));
  expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Plan" })).toHaveAttribute("aria-current", "page");
});

test("marks only the current section as active", () => {
  renderApp("/modules");
  const nav = screen.getByRole("navigation", { name: "Main" });
  const current = nav.querySelectorAll('[aria-current="page"]');
  expect([...current].map((link) => link.textContent)).toEqual(["Modules"]);
});
