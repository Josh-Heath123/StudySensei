import { Check, Copy, Download } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import { Input } from "@/ui/input";

import { useCalendarFeed, useCreateFeed, useDeleteFeed } from "./api";

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const TIME = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/**
 * Settings → Calendar: a private link a calendar app can subscribe to (shown once, with
 * Copy), Reset and Delete for it afterwards, and a Download of the same .ics file.
 */
export function CalendarCard() {
  const feed = useCalendarFeed();
  const create = useCreateFeed();
  const remove = useDeleteFeed();
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function make() {
    const created = await create.mutateAsync(undefined);
    setCopied(false);
    setUrl(created.url);
  }

  async function copy() {
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setCopied(true);
  }

  const state = feed.data;
  return (
    <Card role="region" aria-label="Calendar">
      <CardHeader>
        <CardTitle>Calendar</CardTitle>
        <CardDescription>Your planned blocks in Outlook, Google or Apple Calendar.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {feed.isPending && <div className="skeleton h-9 w-64" aria-label="Loading the calendar" />}
        {feed.isError && (
          <p role="alert" className="text-danger text-sm">
            {feed.error.message}
          </p>
        )}
        {url && (
          <div className="grid gap-2">
            <div className="flex gap-2">
              <Input
                readOnly
                value={url}
                aria-label="Private calendar link"
                className="font-mono"
              />
              <Button variant="outline" onClick={() => void copy()}>
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-warning text-xs font-medium">
              Anyone with this link can see your plan&apos;s topics and times. Reset it if it leaks.
            </p>
            <p className="text-muted text-xs">This is the only time it&apos;s shown.</p>
          </div>
        )}
        {state && !state.exists && !url && (
          <div className="justify-self-start">
            <Button onClick={() => void make()} disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create a private calendar link"}
            </Button>
          </div>
        )}
        {state?.exists && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-muted text-sm tabular-nums">
              Link created {DATE.format(new Date(state.created_at!))} · last fetched{" "}
              {state.last_fetched_at ? TIME.format(new Date(state.last_fetched_at)) : "never"}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmReset(true)}>
                Reset
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
                Delete
              </Button>
            </div>
          </div>
        )}
        {(create.isError || remove.isError) && (
          <p role="alert" className="text-danger text-sm">
            {(create.error ?? remove.error)?.message}
          </p>
        )}
        <div className="grid justify-items-start gap-2">
          <Button variant="outline" size="sm" asChild>
            <a href="/api/calendar/plan.ics" download="studysensei.ics">
              <Download aria-hidden /> Download .ics
            </a>
          </Button>
          <p className="text-muted text-xs">
            Calendar apps can subscribe once StudySensei is hosted; until then, download the file.
          </p>
        </div>
        <ConfirmDialog
          open={confirmReset}
          onOpenChange={setConfirmReset}
          title="Reset the calendar link?"
          description="The old link stops working at once. Calendars subscribed to it need the new one."
          confirmLabel="Reset"
          busyLabel="Resetting…"
          onConfirm={make}
        />
        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title="Delete the calendar link?"
          description="Calendars subscribed to it stop updating. You can create a new one later."
          confirmLabel="Delete"
          busyLabel="Deleting…"
          onConfirm={async () => {
            await remove.mutateAsync(undefined);
            setUrl(null);
          }}
        />
      </CardContent>
    </Card>
  );
}
