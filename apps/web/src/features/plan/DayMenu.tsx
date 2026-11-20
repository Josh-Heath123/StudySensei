import { useState } from "react";

import {
  useCreateException,
  useDeleteException,
  useUpdateException,
  type AvailabilityException,
} from "@/features/settings/api";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  MoreButton,
} from "@/ui/dropdown-menu";

import { dayLabel } from "./week";

type Props = {
  date: string;
  /** Whether the day is marked unavailable (an exception with no windows). */
  unavailable: boolean;
  /** That date's exception, if it has one (custom hours or unavailable). */
  exception: AvailabilityException | undefined;
};

type Pending = "replace" | "restore" | null;

/**
 * docs/DESIGN.md "Day menu": the "…" on a day's header. "Mark unavailable" adds an
 * exception (or, after a confirmation, replaces that day's custom hours); an unavailable day
 * offers "Make available again", which deletes the exception after saying what that means.
 * Each change re-plans on the server.
 */
export function DayMenu({ date, unavailable, exception }: Props) {
  const create = useCreateException();
  const update = useUpdateException();
  const remove = useDeleteException();
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);
  const label = dayLabel(date);

  async function markUnavailable() {
    setError(null);
    if (exception !== undefined) {
      setPending("replace");
      return;
    }
    try {
      await create.mutateAsync({ date, unavailable: true, windows: [] });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <DropdownMenu>
        <MoreButton label={`${label}: options`} className="size-8" />
        <DropdownMenuContent>
          {unavailable ? (
            <DropdownMenuItem onSelect={() => setPending("restore")}>
              Make available again
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem onSelect={() => void markUnavailable()}>
              Mark unavailable
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      {error && (
        <p role="alert" className="text-danger text-xs">
          {error}
        </p>
      )}
      <ConfirmDialog
        open={pending === "replace"}
        onOpenChange={(open) => !open && setPending(null)}
        title={`Mark ${label} unavailable?`}
        description="This replaces the custom hours you set for that day."
        confirmLabel="Mark unavailable"
        busyLabel="Saving…"
        onConfirm={() => update.mutateAsync({ id: exception!.id, unavailable: true, windows: [] })}
      />
      <ConfirmDialog
        open={pending === "restore"}
        onOpenChange={(open) => !open && setPending(null)}
        title={`Make ${label} available again?`}
        description="The day goes back to your weekly hours."
        confirmLabel="Make available"
        busyLabel="Saving…"
        tone="default"
        onConfirm={() => remove.mutateAsync(exception!.id)}
      />
    </>
  );
}
