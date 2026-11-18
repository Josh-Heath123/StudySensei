import { Badge } from "@/ui/badge";

import { useHealth } from "./useHealth";

type Status = "checking" | "ok" | "error" | "unknown";

const LABELS: Record<Status, string> = {
  checking: "Checking…",
  ok: "Connected",
  error: "Not connected",
  unknown: "Unknown",
};

const VARIANTS = {
  checking: "secondary",
  ok: "success",
  error: "destructive",
  unknown: "secondary",
} as const;

function StatusRow({ name, status, detail }: { name: string; status: Status; detail?: string }) {
  return (
    <li className="flex items-center justify-between gap-4 py-1.5">
      <div className="min-w-0">
        <p className="text-fg">{name}</p>
        {detail && <p className="text-muted text-xs break-words">{detail}</p>}
      </div>
      <Badge variant={VARIANTS[status]} aria-label={`${name}: ${LABELS[status]}`}>
        {LABELS[status]}
      </Badge>
    </li>
  );
}

/** Quiet by design (docs/DESIGN.md "Screens: Today"): a small, muted panel, not a card. */
export function SystemStatusCard() {
  const { data, isPending, isError } = useHealth();

  let api: Status = "checking";
  let database: Status = "checking";
  if (isError) {
    api = "error";
    database = "unknown";
  } else if (!isPending) {
    api = "ok";
    database = data.database === "ok" ? "ok" : "error";
  }

  return (
    <div className="border-line rounded-lg border px-4 py-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <p className="text-muted font-semibold">System status</p>
        <p className="text-muted text-xs">Checked every 10 seconds</p>
      </div>
      <ul className="divide-line mt-1 divide-y">
        <StatusRow
          name="API"
          status={api}
          detail={api === "error" ? "Is `npm run dev` running?" : undefined}
        />
        <StatusRow
          name="Database"
          status={database}
          detail={
            database === "error"
              ? `Postgres unreachable (${data?.database_error ?? "unknown error"}). Is Docker running?`
              : undefined
          }
        />
      </ul>
    </div>
  );
}
