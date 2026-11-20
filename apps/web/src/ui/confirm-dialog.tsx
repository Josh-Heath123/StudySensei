import { useState, type ReactNode } from "react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  /** Shown on the button while it works (default "Deleting…"). */
  busyLabel?: string;
  /** "destructive" (default) or "default" for a non-destructive confirmation. */
  tone?: "destructive" | "default";
  onConfirm: () => Promise<unknown>;
};

/** A yes/no dialog (destructive by default). Stays open and shows the error if onConfirm fails. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  busyLabel = "Deleting…",
  tone = "destructive",
  onConfirm,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {error && (
          <p role="alert" className="text-danger text-sm">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={tone === "destructive" ? "destructive" : "default"}
            onClick={confirm}
            disabled={busy}
          >
            {busy ? busyLabel : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
