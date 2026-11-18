import type { CSSProperties } from "react";
import { Link } from "react-router";

import { formatDuration } from "@/session-engine/format";
import { Button } from "@/ui/button";
import { ModuleBadge } from "@/ui/module-badge";

import { useModule } from "../modules/api";
import type { Finished } from "./controller";

/** After the reflection: what the session measured, and the way back to Today. */
export function SessionSummary({ finished }: { finished: Finished }) {
  const module = useModule(finished.moduleId);
  const basis = `Measured · from ${finished.eventCount} timer ${
    finished.eventCount === 1 ? "event" : "events"
  }`;
  const stats = [
    { label: "Active time", value: formatDuration(finished.activeMs) },
    { label: "Break time", value: formatDuration(finished.breakMs) },
  ];

  return (
    <div
      className="mx-auto max-w-[720px] px-4 py-8 sm:px-8 sm:py-12"
      style={{ "--module": module.data?.colour } as CSSProperties}
    >
      <header className="mb-8">
        <p className="type-label text-muted mb-2 flex items-center gap-3">
          {module.data && <ModuleBadge className="normal-case">{module.data.code}</ModuleBadge>}
          Reflection saved
        </p>
        <h1 className="type-h1">Session summary</h1>
      </header>
      <dl className="mb-8 grid gap-4 sm:grid-cols-2">
        {stats.map((stat) => (
          <div key={stat.label} className="surface-card rounded-xl p-5 sm:p-6">
            <dt className="text-sm font-semibold">{stat.label}</dt>
            <dd className="type-countdown mt-2">{stat.value}</dd>
            <dd className="text-muted mt-2 text-xs">{basis}</dd>
          </div>
        ))}
      </dl>
      <Button asChild>
        <Link to="/">Back to Today</Link>
      </Button>
    </div>
  );
}
