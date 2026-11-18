import { PageHeader } from "@/app/PageHeader";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";

import { formatReset, plural, PROVIDER_NAMES, ROLE_ORDER, ROLE_USES } from "./aiSettings";
import {
  type AiModelStatus,
  type AiPingResult,
  type AiStatus,
  useAiStatus,
  usePingModels,
} from "./api";

export function SettingsPage() {
  const status = useAiStatus();
  return (
    <>
      <PageHeader title="Settings" />
      <section aria-labelledby="ai-providers" className="grid gap-6">
        <div>
          <h2 id="ai-providers" className="type-h2">
            AI providers
          </h2>
          <p className="text-muted mt-2">
            The free-tier models StudySensei uses, and how much of today&apos;s allowance is left.
          </p>
        </div>
        {status.isPending && <p className="text-muted">Loading the AI setup…</p>}
        {status.isError && <p className="text-danger">{status.error.message}</p>}
        {status.data && (
          <div className="grid items-start gap-6 lg:grid-cols-2">
            <div className="grid min-w-0 gap-6">
              <ProvidersCard status={status.data} />
              <RolesCard roles={status.data.roles} />
              <PrivacyNote />
            </div>
            <div className="grid min-w-0 gap-6">
              <TestKeysCard models={status.data.models} />
              <UsageCard models={status.data.models} />
            </div>
          </div>
        )}
      </section>
    </>
  );
}

function ProvidersCard({ status }: { status: AiStatus }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Providers</CardTitle>
        <CardDescription>Keys stay on the server and are never shown here.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ul className="divide-line divide-y">
          {status.providers.map((provider) => {
            const name = PROVIDER_NAMES[provider.name] ?? provider.name;
            // Ollama runs locally and needs no key, only a model.
            const label =
              provider.name === "ollama"
                ? provider.configured
                  ? "Model set"
                  : "No model"
                : provider.key_set
                  ? "Key set"
                  : "No key";
            return (
              <li key={provider.name} className="flex items-center justify-between gap-4 py-2">
                <span className="font-semibold">{name}</span>
                <Badge
                  variant={provider.configured ? "success" : "secondary"}
                  aria-label={`${name}: ${label}`}
                >
                  {label}
                </Badge>
              </li>
            );
          })}
        </ul>
        <p className="text-muted text-sm">
          To add one, put <code>GEMINI_API_KEY</code>, <code>GROQ_API_KEY</code> or{" "}
          <code>OLLAMA_MODEL</code> in <code>apps/api/.env</code>, then restart{" "}
          <code>npm run dev</code>.
        </p>
      </CardContent>
    </Card>
  );
}

function RolesCard({ roles }: { roles: Record<string, string[]> }) {
  const names = [...ROLE_ORDER, ...Object.keys(roles).filter((r) => !ROLE_ORDER.includes(r))];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Roles</CardTitle>
        <CardDescription>Each role tries its models in this order.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="divide-line divide-y">
          {names
            .filter((role) => roles[role])
            .map((role) => (
              <div key={role} className="grid gap-1 py-3 first:pt-0 last:pb-0">
                <dt>
                  <span className="font-semibold">{role}</span>
                  <span className="text-muted">: {ROLE_USES[role] ?? "Other work"}</span>
                </dt>
                <dd>
                  <ol
                    className="flex flex-wrap gap-x-2 gap-y-1 text-sm"
                    aria-label={`${role} models`}
                  >
                    {(roles[role] ?? []).map((model, i) => (
                      <li key={model} className="tabular">
                        {i > 0 && (
                          <span className="text-muted mr-2" aria-hidden>
                            →
                          </span>
                        )}
                        {model}
                      </li>
                    ))}
                  </ol>
                </dd>
              </div>
            ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function UsageCard({ models }: { models: AiModelStatus[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Usage today</CardTitle>
        <CardDescription>
          Requests are counted by StudySensei (measured). Daily budgets are estimates: the free-tier
          limits aren&apos;t published.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-line divide-y">
          {models.map((model) => (
            <UsageRow key={`${model.provider}/${model.model}`} model={model} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function UsageRow({ model }: { model: AiModelStatus }) {
  const key = `${model.provider}/${model.model}`;
  const budget = model.daily_budget;
  const used = model.used_today;
  const share = budget ? Math.min(1, used / budget) : 0;
  return (
    <li className="grid gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <span className="font-semibold break-all">{key}</span>
        {!model.configured && <span className="text-muted text-xs">Not set up</span>}
      </div>
      {budget !== null ? (
        <div
          role="meter"
          aria-label={`${key} requests today`}
          aria-valuemin={0}
          aria-valuemax={budget}
          aria-valuenow={Math.min(used, budget)}
          aria-valuetext={`${used} of about ${budget}`}
          className="bg-surface h-2 overflow-hidden rounded-sm"
        >
          <div
            className="bg-ink h-full transition-[width] duration-150 ease-out"
            style={{ width: `${Math.round(share * 1000) / 10}%` }}
          />
        </div>
      ) : null}
      <p className="text-muted tabular text-xs">
        {plural(used, "request")} today (Measured)
        {budget !== null ? (
          <>
            {" "}
            · budget about {budget} a day (Estimated)
            {used >= budget && <span className="text-danger font-semibold"> · Used up</span>}
          </>
        ) : (
          " · no daily limit"
        )}
        {model.resets_at && <> · resets {formatReset(model.resets_at)}</>}
      </p>
    </li>
  );
}

function TestKeysCard({ models }: { models: AiModelStatus[] }) {
  const ping = usePingModels();
  const count = models.filter((m) => m.configured).length;
  return (
    <Card variant="key">
      <CardHeader>
        <CardTitle>Test keys</CardTitle>
        <CardDescription>
          {count > 0
            ? `Sends one short request to each configured model (${plural(count, "request")}), which counts toward today's usage.`
            : "Add a key first: no model is set up yet."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div>
          <Button onClick={() => ping.mutate()} disabled={count === 0 || ping.isPending}>
            {ping.isPending ? "Testing…" : "Test keys"}
          </Button>
        </div>
        {ping.isError && <p className="text-danger text-sm">{ping.error.message}</p>}
        {ping.data && (
          <ul className="divide-line divide-y" aria-label="Test results">
            {ping.data.results.length === 0 && (
              <li className="text-muted py-2 text-sm">No model is set up, so nothing was sent.</li>
            )}
            {ping.data.results.map((result) => (
              <PingRow key={`${result.provider}/${result.model}`} result={result} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

const PING_LABELS = { ok: "OK", failed: "Failed", skipped: "Skipped" } as const;
const PING_VARIANTS = { ok: "success", failed: "destructive", skipped: "warning" } as const;

function PingRow({ result }: { result: AiPingResult }) {
  const key = `${result.provider}/${result.model}`;
  let detail: string;
  if (result.status === "ok") detail = `${result.latency_ms ?? "?"} ms`;
  else if (result.status === "failed") detail = result.error ?? "Unknown error";
  else if (result.resets_at) detail = `Budget used up until ${formatReset(result.resets_at)}`;
  else detail = "Budget used up";
  return (
    <li className="grid gap-1 py-2" aria-label={key}>
      <div className="flex items-center justify-between gap-4">
        <span className="font-semibold break-all">{key}</span>
        <Badge variant={PING_VARIANTS[result.status]}>{PING_LABELS[result.status]}</Badge>
      </div>
      <p className="tabular text-sm break-words">{detail}</p>
      {result.in_models_list === false && (
        <p className="text-warning text-xs">Not in the provider&apos;s model list: check the ID.</p>
      )}
      {result.models_list_error && (
        <p className="text-muted text-xs">
          Couldn&apos;t check the model list: {result.models_list_error}
        </p>
      )}
    </li>
  );
}

function PrivacyNote() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Privacy</CardTitle>
      </CardHeader>
      <CardContent className="text-muted grid gap-2 text-sm">
        <p>
          Free-tier providers may use prompts to improve their models. StudySensei sends course
          content only: never your name, email, student number or reflections.
        </p>
        <p>Materials with Allow AI turned off are never sent.</p>
      </CardContent>
    </Card>
  );
}
