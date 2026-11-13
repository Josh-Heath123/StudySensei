import { Link } from "react-router";

import { Button } from "@/ui/button";

import { ReflectionForm } from "./ReflectionForm";
import { RunningSession } from "./RunningSession";
import { useSession } from "./session";
import { SessionSummary } from "./SessionSummary";

/**
 * /session: the open session, its reflection once it ends, then a summary. It
 * restores from the server (or the local queue), so a reload lands back here.
 */
export function SessionPage() {
  const controller = useSession();
  const state = controller.state();

  switch (state.status) {
    case "loading":
      return <p className="text-muted p-10 text-sm">Loading…</p>;
    case "none":
      return (
        <div className="mx-auto max-w-[720px] px-5 py-10 sm:px-10">
          <h1 className="type-h1 mb-3">No session running</h1>
          <p className="text-muted mb-6">Start one from Today or from a module&apos;s page.</p>
          <Button asChild>
            <Link to="/">Back to Today</Link>
          </Button>
        </div>
      );
    case "open":
      return <RunningSession controller={controller} meta={state.meta} />;
    case "reflecting":
      return <ReflectionForm controller={controller} finished={state.finished} />;
    case "done":
      return <SessionSummary finished={state.finished} />;
  }
}
