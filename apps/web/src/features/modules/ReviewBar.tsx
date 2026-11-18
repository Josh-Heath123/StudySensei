import { CheckCheck, ListFilter, Undo2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";

import { useDismissedTopics, useKeepAllTopics, useRestoreTopic, useTopicMap } from "./api";
import { LoadingRows } from "./LoadingRows";
import { reviewLine, reviewProgress } from "./topicReview";

/**
 * Reviewing the AI's topics (decision 0009): the "Review" filter with its counter,
 * "Keep all remaining", the outcome line, and the dismissed topics with Restore.
 * A floating glass toolbar (docs/DESIGN.md "Glass"): it sticks below the top navigation
 * while the topics section scrolls, so the tree passes underneath it.
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
    <div
      role="region"
      aria-label="Topic review"
      className="glass-strong sticky top-32 z-30 mb-4 grid gap-2 rounded-2xl px-3 py-2.5 sm:top-24 sm:px-4"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button
          size="sm"
          variant={filtering ? "default" : "outline"}
          aria-pressed={filtering}
          onClick={() => onFilter(!filtering)}
        >
          <ListFilter aria-hidden />
          Review
        </Button>
        <span className="tabular text-sm font-medium" aria-live="polite">
          {done} of {total} reviewed
        </span>
        {remaining > 0 && (
          <Button
            size="sm"
            variant="ghost"
            className="sm:ml-auto"
            onClick={() => setConfirmKeepAll(true)}
          >
            <CheckCheck aria-hidden />
            Keep all remaining
          </Button>
        )}
      </div>
      {line && <p className="text-muted px-1 text-sm">{line}</p>}
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
      className="border-line border-t pt-2 text-sm"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="hover:bg-subtle min-h-9 cursor-pointer rounded-md px-1 py-2 font-medium transition-colors">
        Dismissed topics
      </summary>
      <p className="text-muted mt-1 px-1 text-xs">
        Building the topic map again never adds these back. Restore one to bring it back.
      </p>
      {dismissed.isPending && open && (
        <LoadingRows
          label="Loading dismissed topics…"
          rows={2}
          rowClassName="h-9"
          className="mt-2"
        />
      )}
      {(dismissed.isError || restore.isError) && (
        <p role="alert" className="text-danger mt-1 px-1">
          {(dismissed.error ?? restore.error)?.message}
        </p>
      )}
      <ul
        aria-label="Dismissed topics"
        className="divide-line mt-1 grid max-h-48 divide-y overflow-y-auto"
      >
        {dismissed.data?.map((item) => (
          <li key={item.id} className="flex items-center gap-2 py-1 pl-1">
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
