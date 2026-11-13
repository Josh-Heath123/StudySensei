import { Play } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { Button } from "@/ui/button";

import { hasSessionInProgress, useSession } from "./session";
import { StartSessionDialog } from "./StartSessionDialog";

/**
 * The one loud action: start a study session (for `moduleId`, or pick one). If a
 * session is already open, or waiting for its reflection, it returns to it instead.
 */
export function StartSessionButton({ moduleId }: { moduleId?: string }) {
  const controller = useSession();
  const [open, setOpen] = useState(false);

  if (hasSessionInProgress(controller)) {
    return (
      <Button variant="module" asChild>
        <Link to="/session">
          <Play aria-hidden /> Return to session
        </Link>
      </Button>
    );
  }
  return (
    <>
      <Button
        variant="module"
        disabled={controller.state().status === "loading"}
        onClick={() => setOpen(true)}
      >
        <Play aria-hidden /> Start session
      </Button>
      {open && <StartSessionDialog moduleId={moduleId} onClose={() => setOpen(false)} />}
    </>
  );
}
