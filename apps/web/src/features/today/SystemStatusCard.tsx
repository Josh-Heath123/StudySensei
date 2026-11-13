import { Badge } from "@/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";

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
    <li className="flex items-center justify-between gap-4 py-2">
      <div>
        <p className="font-semibold">{name}</p>
        {detail && <p className="text-muted text-xs">{detail}</p>}
      </div>
      <Badge variant={VARIANTS[status]} aria-label={`${name}: ${LABELS[status]}`}>
        {LABELS[status]}
      </Badge>
    </li>
  );
}

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
    <Card>
      <CardHeader>
        <CardTitle>System status</CardTitle>
        <CardDescription>Checked every 10 seconds</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-line divide-y">
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
      </CardContent>
    </Card>
  );
}
