import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { json, mockApi, noContent } from "@/test/mockApi";
import { renderApp } from "@/test/render";

import { aModule, aTopicMap } from "../fixtures";
import type { Material } from "./api";

function aMaterial(overrides: Partial<Material> = {}): Material {
  return {
    id: "mat1",
    module_id: "m1",
    kind: "slides",
    title: "Week 3 slides",
    original_filename: "Week 3 slides.pdf",
    content_type: "application/pdf",
    size_bytes: 2 * 1024 * 1024,
    sha256: "a".repeat(64),
    page_count: null,
    scanned_page_count: null,
    status: "uploaded",
    error: null,
    retrying: false,
    allow_ai: true,
    created_at: "2026-11-13T10:00:00Z",
    updated_at: "2026-11-13T10:00:00Z",
    ...overrides,
  };
}

const file = (name: string, size = 1024) =>
  new File([new Uint8Array(size)], name, { type: "application/octet-stream" });

/** The API, with the materials list served from `list` (tests change it as time passes). */
function serve(list: Material[], routes: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    "GET /modules/:id": () => aModule(),
    "GET /sessions/active": () => null,
    "GET /modules/:id/materials": () => list,
    "GET /modules/:id/topic-map": () => aTopicMap(),
    "GET /modules/:id/topic-map/materials": () => [],
    ...routes,
  });
}

const openTab = () => renderApp("/modules/m1?tab=materials");

test("with nothing uploaded, says so", async () => {
  serve([]);
  openTab();

  expect(await screen.findByText(/No materials yet/)).toBeInTheDocument();
});

test("chosen files are staged with a guessed kind and title; bad ones are refused", async () => {
  serve([]);
  openTab();
  await screen.findByText(/No materials yet/);

  fireEvent.drop(screen.getByTestId("drop-zone"), {
    dataTransfer: {
      files: [file("COS330 Exam 2024.pdf"), file("setup.exe"), file("huge.pdf", 51 * 1024 * 1024)],
    },
  });

  const staged = within(screen.getByRole("list", { name: "Files to upload" }));
  const row = staged.getByRole("listitem", { name: "COS330 Exam 2024.pdf" });
  expect(within(row).getByLabelText("Title")).toHaveValue("COS330 Exam 2024");
  expect(within(row).getByLabelText("Kind")).toHaveValue("past_paper");
  expect(within(row).getByRole("checkbox", { name: "Allow AI processing" })).toBeChecked();
  expect(staged.getAllByRole("listitem")).toHaveLength(1);

  const refused = screen.getByRole("alert");
  expect(refused).toHaveTextContent(".exe files can't be uploaded");
  expect(refused).toHaveTextContent("huge.pdf is 51.0 MB; files can be at most 50 MB.");
  expect(screen.getByRole("button", { name: "Upload 1 file" })).toBeInTheDocument();
});

test("uploads each file as multipart with its kind, title and AI flag, then follows processing", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const list: Material[] = [];
    const { calls } = serve(list, {
      "POST /modules/:id/materials": () => {
        list.push(aMaterial({ title: "My assignment", kind: "assignment", allow_ai: false }));
        return json(list[0], 201);
      },
    });
    openTab();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await screen.findByText(/No materials yet/);

    await user.upload(screen.getByLabelText("Files to upload"), file("submission.docx", 2048));
    const row = screen.getByRole("listitem", { name: "submission.docx" });
    await user.clear(within(row).getByLabelText("Title"));
    await user.type(within(row).getByLabelText("Title"), "My assignment");
    await user.selectOptions(within(row).getByLabelText("Kind"), "assignment");
    await user.click(within(row).getByRole("checkbox", { name: "Allow AI processing" }));
    await user.click(screen.getByRole("button", { name: "Upload 1 file" }));

    const uploaded = await screen.findByRole("listitem", { name: "My assignment" });
    // jsdom drops the part's filename on the way through; e2e/materials.spec.ts checks it
    // in a real browser.
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      file: { name: expect.any(String), size: 2048 },
      kind: "assignment",
      title: "My assignment",
      allow_ai: "false",
    });
    expect(screen.queryByRole("list", { name: "Files to upload" })).not.toBeInTheDocument();
    expect(within(uploaded).getByRole("status")).toHaveTextContent("Waiting to be processed…");

    // The worker picks it up; the list refreshes every 2 s while anything is in flight.
    list[0] = aMaterial({ ...list[0], status: "processing" });
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(within(uploaded).getByRole("status")).toHaveTextContent("Extracting text…");

    list[0] = aMaterial({ ...list[0], status: "ready", page_count: 12, scanned_page_count: 4 });
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(within(uploaded).getByRole("status")).toHaveTextContent(/^Ready$/);
    expect(within(uploaded).getByText("12 pages")).toBeInTheDocument();
    // The scanned count is said once, on the details line.
    expect(within(uploaded).getAllByText(/scanned/)).toHaveLength(1);
    expect(within(uploaded).getByText("4 scanned")).toBeInTheDocument();

    // Nothing in flight: no more polling.
    const before = calls.length;
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(calls.length).toBe(before);
  } finally {
    vi.useRealTimers();
  }
});

test("a duplicate stays staged with the reason", async () => {
  serve([], {
    "POST /modules/:id/materials": () =>
      json({ detail: "This file is already in the module as “Week 3 slides”." }, 409),
  });
  openTab();
  const user = userEvent.setup();
  await screen.findByText(/No materials yet/);

  await user.upload(screen.getByLabelText("Files to upload"), file("week3.pdf"));
  await user.click(screen.getByRole("button", { name: "Upload 1 file" }));

  const row = screen.getByRole("listitem", { name: "week3.pdf" });
  expect(await within(row).findByRole("alert")).toHaveTextContent(
    "Not uploaded: This file is already in the module as “Week 3 slides”.",
  );
});

test("the AI switch, retry and delete act on the material", async () => {
  const list = [
    aMaterial({ id: "ok", title: "Week 1", status: "ready", page_count: 1, scanned_page_count: 0 }),
    aMaterial({
      id: "bad",
      title: "Scanned memo",
      status: "failed",
      error: "The PDF couldn't be opened. It may be damaged or password-protected.",
    }),
    aMaterial({
      id: "slow",
      title: "Week 2",
      status: "processing",
      error: "Something went wrong while processing this file. It will be retried.",
      retrying: true,
    }),
  ];
  const { calls } = serve(list, {
    "PATCH /materials/:id": ({ params, body }) => ({
      ...list.find((m) => m.id === params.id),
      ...(body as object),
    }),
    "POST /materials/:id/retry": ({ params }) => ({
      ...list.find((m) => m.id === params.id),
      status: "uploaded",
      error: null,
    }),
    "DELETE /materials/:id": () => noContent(),
  });
  openTab();
  const user = userEvent.setup();

  const ok = await screen.findByRole("listitem", { name: "Week 1" });
  const bad = screen.getByRole("listitem", { name: "Scanned memo" });
  const slow = screen.getByRole("listitem", { name: "Week 2" });
  expect(within(ok).getByRole("status")).toHaveTextContent("Ready");
  expect(within(ok).getByText("1 page")).toBeInTheDocument();
  expect(within(bad).getByRole("status")).toHaveTextContent(
    "Failed: The PDF couldn't be opened. It may be damaged or password-protected.",
  );
  expect(within(slow).getByRole("status")).toHaveTextContent("Retrying: Something went wrong");
  expect(within(ok).queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();

  await user.click(within(ok).getByRole("checkbox", { name: "Allow AI" }));
  await waitFor(() =>
    expect(calls.find((c) => c.method === "PATCH")).toEqual({
      method: "PATCH",
      path: "/materials/ok",
      body: { allow_ai: false },
    }),
  );

  await user.click(within(bad).getByRole("button", { name: "Retry" }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === "POST" && c.path === "/materials/bad/retry")).toBe(true),
  );

  await user.click(within(ok).getByRole("button", { name: "Delete Week 1" }));
  await user.click(await screen.findByRole("button", { name: "Delete material" }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/materials/ok")).toBe(true),
  );
});

test("View opens the extracted text of a slide deck a page at a time", async () => {
  const material = aMaterial({
    status: "ready",
    page_count: 3,
    scanned_page_count: 1,
    content_type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  });
  const pages = [
    { page_number: 1, title: "Layered architecture", char_count: 40, is_scanned: false },
    { page_number: 2, title: null, char_count: 0, is_scanned: true },
    { page_number: 3, title: "Pipes and filters", char_count: 30, is_scanned: false },
  ];
  const text: Record<string, string> = {
    "1": "Week 3: Layered architecture\nEach layer…",
    "2": "",
    "3": "Pipes and filters\nFilters transform…",
  };
  serve([material], {
    "GET /materials/:id/pages": () => pages,
    "GET /materials/:id/pages/:n": ({ params }) => ({
      ...pages[Number(params.n) - 1],
      text: text[params.n!],
    }),
  });
  openTab();
  const user = userEvent.setup();

  const row = await screen.findByRole("listitem", { name: "Week 3 slides" });
  await user.click(within(row).getByRole("button", { name: "View Week 3 slides" }));

  const dialog = await screen.findByRole("dialog", { name: "Week 3 slides" });
  const first = await within(dialog).findByRole("region", { name: "Page 1 text" });
  expect(await within(first).findByText(/Each layer…/)).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: /Page 1/ })).toHaveAttribute(
    "aria-current",
    "page",
  );

  await user.click(within(dialog).getByRole("button", { name: /Page 2/ }));
  const second = await within(dialog).findByRole("region", { name: "Page 2 text" });
  expect(await within(second).findByText(/No text on this page/)).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: /Page 2/ })).toHaveTextContent("Scanned");

  await user.click(within(dialog).getByRole("button", { name: /Page 3/ }));
  expect(await within(dialog).findByText(/Filters transform…/)).toBeInTheDocument();
});

test("each analysed material shows its topics, and a failed one can be retried", async () => {
  const user = userEvent.setup();
  const slides = aMaterial({ id: "a", title: "CH09 Firewalls", status: "ready" });
  const notes = aMaterial({ id: "b", title: "Chapter 7 notes", status: "ready", kind: "notes" });
  const paper = aMaterial({ id: "c", title: "Exam 2024", status: "ready", kind: "past_paper" });
  let failed = true;
  const { calls } = serve([slides, notes, paper], {
    "GET /modules/:id/topic-map/materials": () => [
      { material_id: "a", state: "analysed", error: null, model: "gemini/x", topics: 7 },
      failed
        ? {
            material_id: "b",
            state: "failed",
            error: "The AI's topic list didn't come out in the expected shape.",
            model: null,
            topics: 0,
          }
        : { material_id: "b", state: "waiting", error: null, model: null, topics: 0 },
    ],
    "POST /materials/:id/topics/retry": () => {
      failed = false;
      return { material_id: "b", state: "waiting", error: null, model: null, topics: 0 };
    },
  });
  openTab();

  const list = await screen.findByRole("list", { name: "Materials" });
  const firewall = within(list).getByRole("listitem", { name: "CH09 Firewalls" });
  expect(await within(firewall).findByText("Topics: 7 found")).toBeVisible();
  const chapter = within(list).getByRole("listitem", { name: "Chapter 7 notes" });
  expect(within(chapter).getByText(/Topics couldn't be found: The AI's topic list/)).toBeVisible();
  // A past paper isn't analysed for topics: no line, no button.
  const exam = within(list).getByRole("listitem", { name: "Exam 2024" });
  expect(within(exam).queryByText(/Topics/)).not.toBeInTheDocument();
  expect(within(firewall).queryByRole("button", { name: /Retry topics/ })).not.toBeInTheDocument();

  await user.click(
    within(chapter).getByRole("button", { name: "Retry topics for Chapter 7 notes" }),
  );

  await waitFor(() =>
    expect(calls.some((c) => c.method === "POST" && c.path === "/materials/b/topics/retry")).toBe(
      true,
    ),
  );
  expect(await within(chapter).findByText("Topics: waiting to be analysed")).toBeVisible();
});
