import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { json, mockApi, noContent } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule } from "./fixtures";

test("lists modules as links to their pages", async () => {
  mockApi({
    "GET /modules": () => [aModule(), aModule({ id: "m2", code: "COS301", name: "Capstone" })],
  });
  renderApp("/modules");

  const link = await screen.findByRole("link", { name: "COS330: Software Architecture, 2026-S2" });
  expect(link).toHaveAttribute("href", "/modules/m1");
  expect(screen.getByRole("link", { name: "COS301: Capstone, 2026-S2" })).toBeInTheDocument();
});

test("shows an empty state with no modules", async () => {
  mockApi({ "GET /modules": () => [] });
  renderApp("/modules");

  expect(await screen.findByText("No modules yet")).toBeInTheDocument();
});

test("creates a module and shows it in the list", async () => {
  let modules = [] as ReturnType<typeof aModule>[];
  const { calls } = mockApi({
    "GET /modules": () => modules,
    "POST /modules": ({ body }) => {
      modules = [aModule(body as object)];
      return json(modules[0], 201);
    },
  });
  renderApp("/modules");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Add your first module" }));
  const dialog = await screen.findByRole("dialog", { name: "New module" });
  await user.type(within(dialog).getByLabelText("Code"), "cos330");
  await user.type(within(dialog).getByLabelText("Name"), "Software Architecture");
  await user.click(within(dialog).getByRole("button", { name: "Colour #34C759" }));
  await user.click(within(dialog).getByRole("button", { name: "Create module" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    code: "cos330",
    name: "Software Architecture",
    colour: "#34C759",
    semester: null,
  });
  expect(await screen.findByRole("link", { name: /Software Architecture/ })).toBeInTheDocument();
});

test("shows a duplicate code (409) under the code field and keeps the dialog open", async () => {
  mockApi({
    "GET /modules": () => [aModule()],
    "POST /modules": () => json({ detail: "You already have a module with the code COS330." }, 409),
  });
  renderApp("/modules");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /New module/ }));
  const dialog = await screen.findByRole("dialog");
  await user.type(within(dialog).getByLabelText("Code"), "cos330");
  await user.type(within(dialog).getByLabelText("Name"), "Again");
  await user.click(within(dialog).getByRole("button", { name: "Create module" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "You already have a module with the code COS330.",
  );
  expect(within(dialog).getByLabelText("Code")).toHaveAttribute("aria-invalid", "true");
});

test("edits a module from its page", async () => {
  let module = aModule();
  const { calls } = mockApi({
    "GET /modules/:id": () => module,
    "GET /modules/:id/topics": () => [],
    "PATCH /modules/:id": ({ body }) => (module = { ...module, ...(body as object) }),
    "GET /modules": () => [module],
  });
  renderApp("/modules/m1");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /Edit/ }));
  const name = within(await screen.findByRole("dialog")).getByLabelText("Name");
  await user.clear(name);
  await user.type(name, "Architecture & Design");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
    name: "Architecture & Design",
  });
});

test("deletes a module after confirming, then returns to the list", async () => {
  const { calls } = mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /modules/:id/topics": () => [],
    "DELETE /modules/:id": () => noContent(),
    "GET /modules": () => [],
  });
  renderApp("/modules/m1");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: /Delete/ }));
  const confirm = await screen.findByRole("dialog", { name: "Delete COS330?" });
  expect(confirm).toHaveTextContent("also deletes all of its topics");
  await user.click(within(confirm).getByRole("button", { name: "Delete module" }));

  expect(await screen.findByText("No modules yet")).toBeInTheDocument();
  expect(calls.some((c) => c.method === "DELETE" && c.path === "/modules/m1")).toBe(true);
});

test("shows a friendly message for a module that doesn't exist", async () => {
  mockApi({ "GET /modules/:id": () => json({ detail: "Module not found" }, 404) });
  renderApp("/modules/nope");

  expect(await screen.findByRole("alert")).toHaveTextContent("This module doesn't exist");
});
