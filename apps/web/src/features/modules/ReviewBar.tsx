import { CheckCheck, ListFilter, Undo2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";

import { useDismissedTopics, useKeepAllTopics, useRestoreTopic, useTopicMap } from "./api";
import { reviewLine, reviewProgress } from "./topicReview";

/**
 * Reviewing the AI's topics (decision 0009): the "Review" filter with its counter,
 * "Keep all remaining", the outcome line, and the dismissed topics with Restore.
 */
export function ReviewBar({
  moduleId,
  filtering,
  onFilter,
}: {
  moduleId: string;
  filtering: boolean;
  onFilter: (on: boolean) => void;
}) {
  const status = useTopicMap(moduleId);
  const keepAll = useKeepAllTopics(moduleId);
  const [confirmKeepAll, setConfirmKeepAll] = useState(false);
  const stats = status.data?.review;
  const { done, total } = reviewProgress(stats);
  const line = reviewLine(stats);
  const remaining = stats?.unreviewed ?? 0;

  if (total === 0) return null;

  return (
    <div role="region" aria-label="Topic review" className="mb-4 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={filtering ? "default" : "outline"}
          aria-pressed={filtering}
          onClick={() => onFilter(!filtering)}
        >
          <ListFilter aria-hidden />
          Review
        </Button>
        <span className="text-sm" aria-live="polite">
          {done} of {total} reviewed
        </span>
        {remaining > 0 && (
          <Button size="sm" variant="ghost" onClick={() => setConfirmKeepAll(true)}>
            <CheckCheck aria-hidden />
            Keep all remaining
          </Button>
        )}
      </div>
      {line && <p className="text-muted text-sm">{line}</p>}
      {(stats?.dismissed ?? 0) > 0 && <DismissedTopics moduleId={moduleId} />}
      <ConfirmDialog
        open={confirmKeepAll}
        onOpenChange={setConfirmKeepAll}
        title={`Keep all ${remaining} remaining AI ${remaining === 1 ? "topic" : "topics"}?`}
        description="Each one becomes yours as it is, and counts as kept. You can still rename, move or delete them afterwards."
        confirmLabel="Keep all"
        onConfirm={() => keepAll.mutateAsync()}
      />
    </div>
  );
}

function DismissedTopics({ moduleId }: { moduleId: string }) {
  const [open, setOpen] = useState(false);
  const dismissed = useDismissedTopics(moduleId, open);
  const restore = useRestoreTopic(moduleId);

  return (
    <details
      className="border-line rounded-md border p-2 text-sm"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer">Dismissed topics</summary>
      <p className="text-muted mt-1 text-xs">
        Building the topic map again never adds these back. Restore one to bring it back.
      </p>
      {dismissed.isPending && open && <p className="text-muted mt-1">Loading…</p>}
      {(dismissed.isError || restore.isError) && (
        <p role="alert" className="text-danger mt-1">
          {(dismissed.error ?? restore.error)?.message}
        </p>
      )}
      <ul aria-label="Dismissed topics" className="mt-1 grid gap-1">
        {dismissed.data?.map((item) => (
          <li key={item.id} className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate">{item.name}</span>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Restore ${item.name}`}
              disabled={restore.isPending}
              onClick={() => restore.mutate(item.id)}
            >
              <Undo2 aria-hidden />
              Restore
            </Button>
          </li>
        ))}
      </ul>
    </details>
  );
}
