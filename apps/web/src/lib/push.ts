/**
 * Web Push in the browser (decision 0024): whether this browser can do it, the permission,
 * and subscribing or unsubscribing this device. The service worker (`/sw.js`) is registered
 * only here, when the student turns reminders on. What the server stores is the subscription
 * (endpoint and keys) and a label for the device; the server decides when to send.
 */

export const SERVICE_WORKER_URL = "/sw.js";

export type Permission = "default" | "granted" | "denied";

/** The subscription as the API takes it (`subscription.toJSON()`). */
export type SubscriptionJson = { endpoint: string; keys: { p256dh: string; auth: string } };

/** Whether this browser has service workers, the Push API and notifications. */
export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function permission(): Permission {
  return Notification.permission as Permission;
}

/** A label for this device from its user agent: "Edge on Windows", "Chrome on Android". */
export function deviceLabel(userAgent: string = navigator.userAgent): string {
  const browser = /Edg\//.test(userAgent)
    ? "Edge"
    : /OPR\//.test(userAgent)
      ? "Opera"
      : /Firefox\//.test(userAgent)
        ? "Firefox"
        : /Chrome\//.test(userAgent)
          ? "Chrome"
          : /Safari\//.test(userAgent)
            ? "Safari"
            : "Browser";
  const system = /Windows/.test(userAgent)
    ? "Windows"
    : /Android/.test(userAgent)
      ? "Android"
      : /iPhone|iPad/.test(userAgent)
        ? "iOS"
        : /Mac OS X/.test(userAgent)
          ? "macOS"
          : /Linux/.test(userAgent)
            ? "Linux"
            : null;
  return system ? `${browser} on ${system}` : browser;
}

/** The VAPID public key (base64url) as the bytes PushManager wants. */
export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4))
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const raw = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

function toJson(subscription: PushSubscription): SubscriptionJson {
  const json = subscription.toJSON();
  return {
    endpoint: json.endpoint ?? subscription.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
  };
}

/** This device's current subscription, if it has one (without registering anything). */
export async function currentSubscription(): Promise<SubscriptionJson | null> {
  const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_URL);
  const subscription = await registration?.pushManager.getSubscription();
  return subscription ? toJson(subscription) : null;
}

/**
 * Ask for permission (call this inside the click, or browsers refuse to ask), register the
 * service worker and subscribe with the server's public key. Returns the subscription, or
 * the permission the student chose if it wasn't granted.
 */
export async function subscribe(publicKey: string): Promise<SubscriptionJson | Permission> {
  const choice = (await Notification.requestPermission()) as Permission;
  if (choice !== "granted") return choice;
  const registration = await navigator.serviceWorker.register(SERVICE_WORKER_URL);
  await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey),
    }));
  return toJson(subscription);
}

/** Unsubscribe this device. Returns the endpoint it had, or null if it had none. */
export async function unsubscribe(): Promise<string | null> {
  const registration = await navigator.serviceWorker.getRegistration(SERVICE_WORKER_URL);
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return null;
  const endpoint = subscription.endpoint;
  await subscription.unsubscribe();
  return endpoint;
}
