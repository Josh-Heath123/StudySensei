import { Layers, Play, Plus } from "lucide-react";
import { useId, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { useModules, type Module, type TopicMastery } from "@/features/modules/api";
import { EmptyState } from "@/features/modules/EmptyState";
import { BAND_LABELS, BAND_VARIANTS } from "@/features/modules/masteryText";
import { useNow } from "@/lib/useNow";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Label } from "@/ui/label";
import { ModuleBadge } from "@/ui/module-badge";
import { NativeSelect } from "@/ui/native-select";

import { useModulesMastery, useQueue, type QueueCounts } from "./api";
import { GenerateButton } from "./GenerateButton";
import { ItemDialog } from "./ItemDialog";
import { fromNow, plural, weakestFirst } from "./practiceText";

type Row = TopicMastery & { module: Module; parentName: string | null };

/**
 * Practice (docs/DESIGN.md "Screens: Practice"): what's due, then every topic with its
 * mastery, weakest first, each with a way to get more practice on it. Mastery is an estimate
 * from the student's own practice and ratings, never an exam prediction.
 */
export function PracticePage() {
  const [params, setParams] = useSearchParams();
  const moduleId = params.get("module") ?? "";
  const modules = useModules();
  const queue = useQueue(moduleId || undefined);
  const shown = (modules.data ?? []).filter((m) => !moduleId || m.id === moduleId);
  const mastery = useModulesMastery(shown.map((m) => m.id));
  const [adding, setAdding] = useState<{ moduleId?: string; topicId?: string } | null>(null);
  const [message, setMessage] = useState("");
  const filterId = useId();

  const rows: Row[] = weakestFirst(
    mastery.flatMap((result, index) => {
      const module = shown[index]!;
      const topics = result.data?.topics ?? [];
      const names = new Map(topics.map((t) => [t.topic_id, t.name]));
      return topics.map((t) => ({
        ...t,
        module,
        parentName: t.parent_id ? (names.get(t.parent_id) ?? null) : null,
      }));
    }),
  );
  const loading = modules.isPending || mastery.some((m) => m.isPending);
  const failed = modules.error ?? mastery.find((m) => m.isError)?.error;
  const review = `/practice/review${moduleId ? `?module=${moduleId}` : ""}`;
  const items = `/practice/items${moduleId ? `?module=${moduleId}` : ""}`;

  return (
    <>
      <PageHeader
        title="Practice"
        description="Spaced reviews of your cards and questions. Mastery below is an estimate from your own practice and ratings, never an exam prediction."
        aside={
          <>
            <Button asChild variant="outline">
              <Link to={items}>All items</Link>
            </Button>
            <Button asChild>
              <Link to={review}>
                <Play aria-hidden />
                Start review
              </Link>
            </Button>
          </>
        }
      />
      <QueueTiles counts={queue.data?.counts} error={queue.error?.message} />

      <section aria-labelledby="topics-heading" className="mt-10 grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 id="topics-heading" className="type-h2">
              Topics
            </h2>
            <p className="text-muted mt-1 text-sm">Weakest first.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor={filterId}>Module</Label>
              <NativeSelect
                id={filterId}
                value={moduleId}
                className="w-64 max-w-full"
                onChange={(event) =>
                  setParams(event.target.value ? { module: event.target.value } : {})
                }
              >
                <option value="">All modules</option>
                {modules.data?.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} {m.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button
              variant="outline"
              onClick={() => setAdding({ moduleId: moduleId || undefined })}
            >
              <Plus aria-hidden />
              Add a card
            </Button>
          </div>
        </div>
        <p aria-live="polite" className="text-success text-sm empty:hidden">
          {message}
        </p>
        {failed ? (
          <p role="alert" className="text-danger">
            Couldn&apos;t load your topics: {failed.message}
          </p>
        ) : loading ? (
          <div aria-busy="true" className="grid gap-3">
            <p className="sr-only">Loading…</p>
            {[0, 1, 2].map((n) => (
              <div key={n} className="skeleton h-24 rounded-lg" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No topics yet"
            action={
              <Button asChild variant="outline">
                <Link to="/modules">Go to modules</Link>
              </Button>
            }
          >
            Add a module and build its topic map; each topic then gets its own practice here.
          </EmptyState>
        ) : (
          <ul className="grid gap-3">
            {rows.map((row) => (
              <TopicRow
                key={row.topic_id}
                row={row}
                showModule={!moduleId && shown.length > 1}
                onAdd={() => setAdding({ moduleId: row.module.id, topicId: row.topic_id })}
              />
            ))}
          </ul>
        )}
      </section>
      {adding && (
        <ItemDialog
          moduleId={adding.moduleId}
          topicId={adding.topicId}
          onClose={() => setAdding(null)}
          onSaved={setMessage}
        />
      )}
    </>
  );
}

function QueueTiles({ counts, error }: { counts: QueueCounts | undefined; error?: string }) {
  const now = useNow();
  if (error) {
    return (
      <p role="alert" className="text-danger">
        Couldn&apos;t load your reviews: {error}
      </p>
    );
  }
  const tiles = [
    {
      label: "Due now",
      value: counts ? String(counts.due_now) : "…",
      note: "Cards whose review time has come",
    },
    {
      label: "New today",
      value: counts ? String(counts.new_today_left) : "…",
      note: counts
        ? `${counts.new_allowance_left} of today's new allowance left · ${plural(counts.new_total, "new card")} waiting`
        : "",
    },
    {
      label: "Next due",
      value: !counts
        ? "…"
        : counts.next_due_at
          ? fromNow(counts.next_due_at, now)
          : "Nothing scheduled",
      note: counts?.due_now ? "After the ones due now" : "Your next review",
    },
  ];
  return (
    <dl aria-label="Reviews" className="grid gap-3 sm:grid-cols-3">
      {tiles.map((tile) => (
        <div key={tile.label} className="surface-card grid gap-1 rounded-lg p-4">
          <dt className="type-label text-muted">{tile.label}</dt>
          <dd className="type-h2 tabular-nums">{tile.value}</dd>
          <dd className="text-muted text-xs">{tile.note}</dd>
        </div>
      ))}
    </dl>
  );
}

function TopicRow({
  row,
  showModule,
  onAdd,
}: {
  row: Row;
  showModule: boolean;
  onAdd: () => void;
}) {
  const s = row.samples;
  const itemsLink = `/practice/items?module=${row.module.id}&topic=${row.topic_id}`;
  return (
    <li className="surface-card grid gap-3 rounded-lg p-4 sm:p-5">
      <div className="grid min-w-0 gap-1">
        <div className="flex flex-wrap items-center gap-2">
          {showModule && <ModuleBadge module={row.module} />}
          <h3 className="type-h3 [overflow-wrap:anywhere]">
            {row.parentName && <span className="text-muted font-normal">{row.parentName} › </span>}
            {row.name}
          </h3>
          {row.band && <Badge variant={BAND_VARIANTS[row.band]}>{BAND_LABELS[row.band]}</Badge>}
        </div>
        <p className="text-muted text-sm">{row.basis}</p>
        <Link to={itemsLink} className="text-link justify-self-start text-sm hover:underline">
          {plural(s.items_active, "active item")}
          {s.items_reviewed > 0 && `, ${s.items_reviewed} reviewed`}
        </Link>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <GenerateButton topicId={row.topic_id} topicName={row.name} />
        <Button variant="quiet" size="sm" onClick={onAdd} aria-label={`Add a card to ${row.name}`}>
          <Plus aria-hidden />
          Add a card
        </Button>
      </div>
    </li>
  );
}
