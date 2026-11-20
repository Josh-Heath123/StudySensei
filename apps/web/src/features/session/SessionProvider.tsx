import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import type { SessionController } from "./controller";
import { createBrowserController, SessionContext } from "./session";

/** Holds the one session controller for the app (tests can pass their own). */
export function SessionProvider({
  children,
  controller,
}: {
  children: ReactNode;
  controller?: SessionController;
}) {
  const [value] = useState(() => controller ?? createBrowserController());
  const queryClient = useQueryClient();
  // Starting or finishing a session changes the plan (a linked block, a done block, a
  // re-plan): refetch it when the session's status changes.
  useEffect(() => {
    let status = value.state().status;
    return value.subscribe(() => {
      const next = value.state().status;
      if (next !== status && status !== "loading") {
        void queryClient.invalidateQueries({ queryKey: ["plan"] });
      }
      status = next;
    });
  }, [value, queryClient]);
  return <SessionContext value={value}>{children}</SessionContext>;
}
