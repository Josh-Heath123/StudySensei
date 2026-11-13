import { useState } from "react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";

import type { SessionController } from "./controller";

/**
 * "You were away": the one question that blocks the screen, because the clock
 * can't be trusted until it's answered. It can't be dismissed without a choice.
 */
export function AwayDialog({
  message,
  controller,
}: {
  message: string;
  controller: SessionController;
}) {
  const [busy, setBusy] = useState(false);
  const choose = (choice: "keep" | "pause" | "end") => {
    setBusy(true);
    void controller.resolveAway(choice).finally(() => setBusy(false));
  };
  const stay = (event: Event) => event.preventDefault();

  return (
    <Dialog open>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={stay}
        onPointerDownOutside={stay}
        onInteractOutside={stay}
      >
        <DialogHeader>
          <DialogTitle>Were you away?</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => choose("keep")}>
            Keep the time
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => choose("end")}>
            End from when I left
          </Button>
          <Button disabled={busy} onClick={() => choose("pause")}>
            Pause from when I left
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
