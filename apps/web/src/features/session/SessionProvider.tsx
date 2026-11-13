import { useState, type ReactNode } from "react";

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
  return <SessionContext value={value}>{children}</SessionContext>;
}
