import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { deviceLabel, keyBytes } from "@/lib/push";
import { fakeStudyTime } from "@/test/fakeStudyTime";
import { json, mockApi, noContent, type ApiCall, type Handler } from "@/test/mockApi";
import { renderApp } from "@/test/render";

const SUBSCRIPTION = {
  endpoint: "https://push.example/this-browser",
  keys: { p256dh: "BThisKey", auth: "ThisAuth" },
};

/**
 * A browser with Notification, PushManager and a service worker, all in memory.
 * `choice` is what requestPermission answers; `subscribed` whether a subscription exists.
 */
function fakeBrowser({
  permission = "default" as NotificationPermission,
  choice = "granted" as NotificationPermission,
  subscribed = false,
} = {}) {
  const state = { permission, subscribed, registered: false, unsubscribed: false };
  const subscription = {
    endpoint: SUBSCRIPTION.endpoint,
    toJSON: () => SUBSCRIPTION,
    unsubscribe: vi.fn(async () => {
      state.subscribed = false;
      state.unsubscribed = true;
      return true;
    }),
  };
  const pushManager = {
    getSubscription: vi.fn(async () => (state.subscribed ? subscription : null)),
    subscribe: vi.fn(async () => {
      state.subscribed = true;
      return subscription;
    }),
  };
  const registration = { pushManager };
  class FakeNotification {
    static get permission() {
      return state.permission;
    }
    static requestPermission = vi.fn(async () => {
      state.permission = choice;
      return choice;
    });
  }
  vi.stubGlobal("Notification", FakeNotification);
  vi.stubGlobal("PushManager", class {});
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      register: vi.fn(async () => {
        state.registered = true;
        return registration;
      }),
      getRegistration: vi.fn(async () =>
        state.registered || state.subscribed ? registration : undefined,
      ),
      ready: Promise.resolve(registration),
    },
  });
  return { state, pushManager, FakeNotification };
}

afterEach(() => {
  // @ts-expect-error: undo the fake service worker container
  delete navigator.serviceWorker;
});

function renderSettings(routes: Record<string, Handler> = {}) {
  const devices = [
    {
      id: "this",
      label: "Edge on Windows",
      created_at: "2026-11-20T08:00:00Z",
      last_success_at: null,
    },
    {
      id: "phone",
      label: "Chrome on Android",
      created_at: "2026-11-19T08:00:00Z",
      last_success_at: null,
    },
  ];
  const api = mockApi({
    ...fakeStudyTime().routes,
    "GET /ai/status": () => json({ detail: "not in this test" }, 503),
    "GET /push/config": () => ({ enabled: true, public_key: "BPub_Key-12x" }),
    "POST /push/subscriptions": () => json(devices[0], 201),
    "GET /push/subscriptions": () => devices,
    "DELETE /push/subscriptions/:id": () => noContent(),
    "POST /push/test": () => ({
      devices: [
        { id: "this", label: "Edge on Windows", outcome: "sent" },
        { id: "phone", label: "Chrome on Android", outcome: "removed" },
      ],
    }),
    ...routes,
  });
  renderApp("/settings");
  return { ...api, user: userEvent.setup() };
}

const card = () => screen.findByRole("region", { name: "Reminders" });

const sent = (calls: ApiCall[], method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path === path);

test("a browser without push says so", async () => {
  // jsdom has no service worker or PushManager.
  renderSettings();
  expect(
    await within(await card()).findByText(/This browser can't show reminders/),
  ).toBeInTheDocument();
});

test("with no VAPID keys on the server it says reminders aren't set up", async () => {
  fakeBrowser();
  renderSettings({ "GET /push/config": () => ({ enabled: false, public_key: null }) });
  const reminders = await card();
  expect(
    await within(reminders).findByText(/Reminders aren't set up on the server yet/),
  ).toBeInTheDocument();
  expect(within(reminders).queryByRole("button")).toBeNull();
});

test("turning on asks in the click, subscribes with the server's key and saves the device", async () => {
  const browser = fakeBrowser();
  const { user, calls } = renderSettings();
  const reminders = await card();
  await user.click(
    await within(reminders).findByRole("button", { name: "Turn on reminders on this device" }),
  );

  expect(browser.FakeNotification.requestPermission).toHaveBeenCalledOnce();
  expect(browser.pushManager.subscribe).toHaveBeenCalledWith({
    userVisibleOnly: true,
    applicationServerKey: keyBytes("BPub_Key-12x"),
  });
  await waitFor(() => expect(sent(calls, "POST", "/push/subscriptions")).toHaveLength(1));
  expect(sent(calls, "POST", "/push/subscriptions")[0]!.body).toEqual({
    ...SUBSCRIPTION,
    label: deviceLabel(),
  });
  // On: this device, the lead time, a test, and the other device with Remove.
  expect(await within(reminders).findByText("This device")).toBeInTheDocument();
  expect(within(reminders).getByLabelText("Remind me")).toHaveValue("10");
  expect(
    within(reminders).getByRole("button", { name: "Remove Chrome on Android" }),
  ).toBeInTheDocument();
});

test("denied: how to allow notifications", async () => {
  fakeBrowser({ choice: "denied" });
  const { user, calls } = renderSettings();
  const reminders = await card();
  await user.click(
    await within(reminders).findByRole("button", { name: "Turn on reminders on this device" }),
  );
  expect(await within(reminders).findByText(/Notifications are blocked/)).toBeInTheDocument();
  expect(within(reminders).getByText(/set Notifications\s+to Allow/)).toBeInTheDocument();
  expect(sent(calls, "POST", "/push/subscriptions")).toHaveLength(0);
});

test("already blocked: the same help, with no button", async () => {
  fakeBrowser({ permission: "denied" });
  renderSettings();
  const reminders = await card();
  expect(await within(reminders).findByText(/Notifications are blocked/)).toBeInTheDocument();
  expect(within(reminders).queryByRole("button")).toBeNull();
});

test("on: the lead time, a test with each device's outcome, removing another device", async () => {
  fakeBrowser({ permission: "granted", subscribed: true });
  const { user, calls } = renderSettings();
  const reminders = await card();
  expect(await within(reminders).findByText("This device")).toBeInTheDocument();
  // Its subscription was saved again to find its id.
  expect(sent(calls, "POST", "/push/subscriptions")).toHaveLength(1);

  await user.selectOptions(within(reminders).getByLabelText("Remind me"), "30");
  await waitFor(() => expect(sent(calls, "PATCH", "/planning/settings")).toHaveLength(1));
  expect(sent(calls, "PATCH", "/planning/settings")[0]!.body).toEqual({ reminder_minutes: 30 });
  await user.selectOptions(within(reminders).getByLabelText("Remind me"), "off");
  await waitFor(() =>
    expect(sent(calls, "PATCH", "/planning/settings")[1]!.body).toEqual({ reminder_minutes: null }),
  );

  await user.click(within(reminders).getByRole("button", { name: "Send a test" }));
  const result = await within(reminders).findByRole("status");
  expect(result).toHaveTextContent("Edge on Windows: sent");
  expect(result).toHaveTextContent("Chrome on Android: is no longer subscribed, so it was removed");

  await user.click(within(reminders).getByRole("button", { name: "Remove Chrome on Android" }));
  await waitFor(() => expect(sent(calls, "DELETE", "/push/subscriptions/phone")).toHaveLength(1));
});

test("turning off unsubscribes this browser, then deletes its device", async () => {
  const browser = fakeBrowser({ permission: "granted", subscribed: true });
  const { user, calls } = renderSettings();
  const reminders = await card();
  await user.click(
    await within(reminders).findByRole("button", { name: "Turn off on this device" }),
  );
  await waitFor(() => expect(sent(calls, "DELETE", "/push/subscriptions/this")).toHaveLength(1));
  expect(browser.state.unsubscribed).toBe(true);
  expect(
    await within(reminders).findByRole("button", { name: "Turn on reminders on this device" }),
  ).toBeInTheDocument();
});

test("device labels come from the user agent", () => {
  expect(
    deviceLabel(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0",
    ),
  ).toBe("Edge on Windows");
  expect(
    deviceLabel(
      "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36",
    ),
  ).toBe("Chrome on Android");
  expect(
    deviceLabel("Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"),
  ).toBe("Firefox on Linux");
});

// --- the calendar card ---------------------------------------------------------------

function calendarRoutes() {
  let feed = {
    exists: false,
    created_at: null as string | null,
    last_fetched_at: null as string | null,
  };
  let made = 0;
  return {
    "GET /calendar/feed": () => feed,
    "POST /calendar/feed": () => {
      made += 1;
      feed = { exists: true, created_at: "2026-11-20T08:00:00Z", last_fetched_at: null };
      return json(
        {
          url: `http://localhost:5173/api/calendar/token-${made}.ics`,
          created_at: feed.created_at,
        },
        201,
      );
    },
    "DELETE /calendar/feed": () => {
      feed = { exists: false, created_at: null, last_fetched_at: null };
      return noContent();
    },
  } satisfies Record<string, Handler>;
}

const calendarCard = () => screen.findByRole("region", { name: "Calendar" });

test("create a link: shown once with Copy and the warning; then its state, Reset and Delete", async () => {
  const writeText = vi.fn(async () => undefined);
  const { user, calls } = renderSettings(calendarRoutes());
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const calendar = await calendarCard();
  expect(within(calendar).getByRole("link", { name: "Download .ics" })).toHaveAttribute(
    "href",
    "/api/calendar/plan.ics",
  );
  expect(calendar).toHaveTextContent(
    "Calendar apps can subscribe once StudySensei is hosted; until then, download the file.",
  );

  await user.click(
    await within(calendar).findByRole("button", { name: "Create a private calendar link" }),
  );
  const link = await within(calendar).findByLabelText("Private calendar link");
  expect(link).toHaveValue("http://localhost:5173/api/calendar/token-1.ics");
  expect(calendar).toHaveTextContent(
    "Anyone with this link can see your plan's topics and times. Reset it if it leaks.",
  );
  await user.click(within(calendar).getByRole("button", { name: "Copy" }));
  expect(writeText).toHaveBeenCalledWith("http://localhost:5173/api/calendar/token-1.ics");
  expect(await within(calendar).findByText(/last fetched never/)).toBeInTheDocument();

  // Reset asks first, then shows the new link.
  await user.click(within(calendar).getByRole("button", { name: "Reset" }));
  const confirm = await screen.findByRole("dialog", { name: "Reset the calendar link?" });
  expect(sent(calls, "POST", "/calendar/feed")).toHaveLength(1);
  await user.click(within(confirm).getByRole("button", { name: "Reset" }));
  await waitFor(() =>
    expect(within(calendar).getByLabelText("Private calendar link")).toHaveValue(
      "http://localhost:5173/api/calendar/token-2.ics",
    ),
  );

  await user.click(within(calendar).getByRole("button", { name: "Delete" }));
  await user.click(
    within(await screen.findByRole("dialog", { name: "Delete the calendar link?" })).getByRole(
      "button",
      { name: "Delete" },
    ),
  );
  expect(
    await within(calendar).findByRole("button", { name: "Create a private calendar link" }),
  ).toBeInTheDocument();
  expect(within(calendar).queryByLabelText("Private calendar link")).toBeNull();
});

test("an existing link shows when it was created and last fetched, never the URL", async () => {
  renderSettings({
    "GET /calendar/feed": () => ({
      exists: true,
      created_at: "2026-11-18T08:00:00Z",
      last_fetched_at: "2026-11-20T09:30:00Z",
    }),
  });
  const calendar = await calendarCard();
  expect(
    await within(calendar).findByText(/Link created 18 Nov 2026 · last fetched Fri/),
  ).toBeInTheDocument();
  expect(within(calendar).queryByLabelText("Private calendar link")).toBeNull();
  expect(
    within(calendar).queryByRole("button", { name: "Create a private calendar link" }),
  ).toBeNull();
});
