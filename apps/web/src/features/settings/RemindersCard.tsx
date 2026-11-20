import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import {
  currentSubscription,
  deviceLabel,
  permission,
  pushSupported,
  subscribe,
  unsubscribe,
} from "@/lib/push";
import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";

import {
  type PushDevice,
  type PushTestResult,
  usePlanningSettings,
  usePushConfig,
  usePushDevices,
  useRemoveDevice,
  useSaveDevice,
  useSetReminderMinutes,
  useTestPush,
} from "./api";

/** This browser's state: one of the card's states (docs/DESIGN.md "Reminders card"). */
type ThisDevice =
  { kind: "unsupported" } | { kind: "off" } | { kind: "denied" } | { kind: "on"; id: string };

const LEADS = [
  { value: "off", label: "Off" },
  { value: "5", label: "5 min before" },
  { value: "10", label: "10 min before" },
  { value: "15", label: "15 min before" },
  { value: "30", label: "30 min before" },
] as const;

const thisDeviceKey = ["push", "this-device"] as const;

/**
 * Where this browser stands. A subscription it already has is saved again (the server
 * upserts by endpoint), which finds its id for "This device" and repairs one the server
 * dropped after failures.
 */
async function readThisDevice(): Promise<ThisDevice> {
  if (!pushSupported()) return { kind: "unsupported" };
  if (permission() === "denied") return { kind: "denied" };
  if (permission() !== "granted") return { kind: "off" };
  const subscription = await currentSubscription();
  if (!subscription) return { kind: "off" };
  const saved = await unwrap(
    api.POST("/push/subscriptions", { body: { ...subscription, label: deviceLabel() } }),
  );
  return { kind: "on", id: saved.id };
}

/**
 * Settings → Reminders: a push notification before each planned block, on the devices the
 * student turns it on for. One state at a time: not supported here, not set up on the
 * server, not asked yet, blocked, or on (this device, the lead time, a test, other devices).
 */
export function RemindersCard() {
  const config = usePushConfig();
  const enabled = config.data?.enabled ?? false;
  const queryClient = useQueryClient();
  const device = useQuery({
    queryKey: thisDeviceKey,
    queryFn: readThisDevice,
    enabled,
    retry: false,
  });
  const save = useSaveDevice();
  const remove = useRemoveDevice();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function turnOn() {
    setError(null);
    setBusy(true);
    try {
      const result = await subscribe(config.data!.public_key!);
      if (typeof result === "string") {
        queryClient.setQueryData(thisDeviceKey, {
          kind: result === "denied" ? "denied" : "off",
        } satisfies ThisDevice);
        return;
      }
      const saved = await save.mutateAsync({ ...result, label: deviceLabel() });
      queryClient.setQueryData(thisDeviceKey, { kind: "on", id: saved.id } satisfies ThisDevice);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function turnOff(id: string) {
    setError(null);
    setBusy(true);
    try {
      await unsubscribe();
      await remove.mutateAsync(id);
      queryClient.setQueryData(thisDeviceKey, { kind: "off" } satisfies ThisDevice);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  let body: React.ReactNode;
  if (!pushSupported()) {
    body = (
      <p className="text-muted text-sm">
        This browser can&apos;t show reminders. Try Edge, Chrome or Firefox on a computer or Android
        phone.
      </p>
    );
  } else if (config.isPending || (enabled && device.isPending)) {
    body = <div className="skeleton h-9 w-56" aria-label="Loading reminders" />;
  } else if (config.isError || device.isError) {
    body = (
      <p role="alert" className="text-danger text-sm">
        {(config.error ?? device.error)?.message}
      </p>
    );
  } else if (!enabled) {
    body = (
      <p className="text-muted text-sm">
        Reminders aren&apos;t set up on the server yet. Run{" "}
        <code className="font-mono text-xs">uv run python -m app.push.keys</code> in apps/api, paste
        its three lines into apps/api/.env, and restart the API and worker.
      </p>
    );
  } else if (device.data?.kind === "denied") {
    body = (
      <div className="grid gap-2 text-sm">
        <p className="font-medium">Notifications are blocked for StudySensei in this browser.</p>
        <p className="text-muted">
          To allow them, open the site settings (the icon left of the address), set Notifications to
          Allow, then reload this page.
        </p>
      </div>
    );
  } else if (device.data?.kind === "on") {
    body = <OnState deviceId={device.data.id} busy={busy} onTurnOff={turnOff} />;
  } else {
    body = (
      <div className="grid justify-items-start gap-3">
        <p className="text-muted text-sm">
          A notification a few minutes before each planned block, on this device.
        </p>
        <Button onClick={() => void turnOn()} disabled={busy}>
          <BellRing aria-hidden /> {busy ? "Turning on…" : "Turn on reminders on this device"}
        </Button>
      </div>
    );
  }

  return (
    <Card role="region" aria-label="Reminders">
      <CardHeader>
        <CardTitle>Reminders</CardTitle>
        <CardDescription>
          Each one names the topic and the time, nothing else, and is encrypted on its way to your
          browser.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {body}
        {error && (
          <p role="alert" className="text-danger text-sm">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function OnState({
  deviceId,
  busy,
  onTurnOff,
}: {
  deviceId: string;
  busy: boolean;
  onTurnOff: (id: string) => Promise<void>;
}) {
  const settings = usePlanningSettings();
  const setLead = useSetReminderMinutes();
  const devices = usePushDevices();
  const test = useTestPush();
  const remove = useRemoveDevice();
  const [result, setResult] = useState<PushTestResult | null>(null);
  const lead = settings.data?.reminder_minutes;
  const others = (devices.data ?? []).filter((d) => d.id !== deviceId);
  const mine = devices.data?.find((d) => d.id === deviceId);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          <span className="font-medium">{mine?.label ?? "This device"}</span>{" "}
          <span className="text-success text-xs font-semibold">This device</span>
        </p>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => void onTurnOff(deviceId)}>
          {busy ? "Turning off…" : "Turn off on this device"}
        </Button>
      </div>
      <div className="grid max-w-xs gap-1.5">
        <Label htmlFor="reminder-lead">Remind me</Label>
        <NativeSelect
          id="reminder-lead"
          value={lead === undefined ? "10" : lead === null ? "off" : String(lead)}
          disabled={settings.isPending || setLead.isPending}
          onChange={(e) => {
            const value = e.target.value;
            setLead.mutate(value === "off" ? null : (Number(value) as 5 | 10 | 15 | 30));
          }}
        >
          {LEADS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </NativeSelect>
        {lead === null && <p className="text-muted text-xs">Off: no reminders on any device.</p>}
      </div>
      <div className="grid justify-items-start gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={test.isPending}
          onClick={() => {
            setResult(null);
            test.mutate(undefined, { onSuccess: setResult });
          }}
        >
          {test.isPending ? "Sending…" : "Send a test"}
        </Button>
        {result && <TestResult result={result} />}
        {test.isError && (
          <p role="alert" className="text-danger text-sm">
            {test.error.message}
          </p>
        )}
      </div>
      {others.length > 0 && (
        <div className="grid gap-2">
          <h3 className="type-label text-muted">Other devices</h3>
          <ul className="grid gap-2">
            {others.map((d) => (
              <OtherDevice
                key={d.id}
                device={d}
                busy={remove.isPending}
                onRemove={() => remove.mutate(d.id)}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function OtherDevice({
  device,
  busy,
  onRemove,
}: {
  device: PushDevice;
  busy: boolean;
  onRemove: () => void;
}) {
  return (
    <li className="border-line flex items-center justify-between gap-3 rounded-md border px-3 py-2">
      <span className="min-w-0 truncate text-sm">{device.label}</span>
      <Button
        variant="ghost"
        size="sm"
        disabled={busy}
        aria-label={`Remove ${device.label}`}
        onClick={onRemove}
      >
        Remove
      </Button>
    </li>
  );
}

const OUTCOME_TEXT = {
  sent: "sent",
  failed: "didn't arrive (it will be tried again next time)",
  removed: "is no longer subscribed, so it was removed",
} as const;

function TestResult({ result }: { result: PushTestResult }) {
  if (result.devices.length === 0) {
    return <p className="text-muted text-sm">No devices to send to.</p>;
  }
  return (
    <ul role="status" className="text-muted grid gap-1 text-sm">
      {result.devices.map((d) => (
        <li key={d.id}>
          {d.label}: {OUTCOME_TEXT[d.outcome]}
        </li>
      ))}
    </ul>
  );
}
