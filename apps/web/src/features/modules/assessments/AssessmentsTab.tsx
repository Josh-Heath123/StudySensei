import { CalendarClock, ClipboardList, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { formatDue, relativeDay } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/ui/dialog";

import {
  KIND_LABELS,
  STATUS_LABELS,
  useAssessments,
  useCreateAssessment,
  useDeleteAssessment,
  useUpdateAssessment,
  type Assessment,
} from "./api";
import { EmptyState } from "../EmptyState";
import { LoadingRows } from "../LoadingRows";
import { AssessmentForm } from "./AssessmentForm";

export function AssessmentsTab({ moduleId }: { moduleId: string }) {
  const assessments = useAssessments(moduleId);
  const create = useCreateAssessment(moduleId);
  const update = useUpdateAssessment();
  const remove = useDeleteAssessment();
  // null = closed, "new" = create dialog, otherwise the assessment being edited.
  const [editing, setEditing] = useState<Assessment | "new" | null>(null);
  const [toDelete, setToDelete] = useState<Assessment | null>(null);

  const items = assessments.data ?? [];
  // Cancelled assessments don't count towards the module's marks.
  const weighted = items.filter((a) => a.status !== "cancelled" && a.weight !== null);
  const total = weighted.reduce((sum, a) => sum + (a.weight ?? 0), 0);

  return (
    <section aria-labelledby="assessments-heading">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-1 basis-64">
          <h2 id="assessments-heading" className="type-h2 mb-1">
            Assessments
          </h2>
          <p className="text-muted max-w-2xl text-sm">
            Exams, tests and assignments, with their dates, weights and the topics they cover.
          </p>
        </div>
        <Button variant="outline" onClick={() => setEditing("new")}>
          <Plus aria-hidden /> Add assessment
        </Button>
      </div>

      {assessments.isPending && <LoadingRows label="Loading assessments…" />}
      {assessments.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load assessments: {assessments.error.message}
        </p>
      )}
      {assessments.data?.length === 0 && (
        <EmptyState icon={ClipboardList}>
          No assessments yet. Add the module's exams, tests and assignments from the study guide.
        </EmptyState>
      )}

      {items.length > 0 && (
        <>
          <ul
            aria-label="Assessments"
            className="surface-card divide-line divide-y overflow-hidden rounded-xl"
          >
            {items.map((assessment) => (
              <AssessmentRow
                key={assessment.id}
                assessment={assessment}
                onEdit={() => setEditing(assessment)}
                onDelete={() => setToDelete(assessment)}
              />
            ))}
          </ul>
          {weighted.length > 0 && (
            <p className="text-muted mt-3 px-1 text-right text-sm">
              Weights total <span className="text-fg tabular font-semibold">{total}%</span>
              {total !== 100 && <span className="text-warning"> (not 100%)</span>}
            </p>
          )}
        </>
      )}

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {editing === "new" ? "Add assessment" : `Edit ${editing?.title ?? ""}`}
            </DialogTitle>
          </DialogHeader>
          {editing !== null && (
            <AssessmentForm
              moduleId={moduleId}
              initial={editing === "new" ? undefined : editing}
              submitLabel={editing === "new" ? "Add assessment" : "Save changes"}
              onCancel={() => setEditing(null)}
              onSubmit={async (values) => {
                if (editing === "new") {
                  await create.mutateAsync(values);
                } else {
                  await update.mutateAsync({ id: editing.id, changes: values });
                }
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(open) => !open && setToDelete(null)}
        title={`Delete “${toDelete?.title ?? ""}”?`}
        description="Tasks linked to it are kept, just no longer linked."
        confirmLabel="Delete assessment"
        onConfirm={() => remove.mutateAsync(toDelete!.id)}
      />
    </section>
  );
}

function AssessmentRow({
  assessment,
  onEdit,
  onDelete,
}: {
  assessment: Assessment;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { title, kind, due_at, weight, status, topic_ids } = assessment;
  const done = status !== "upcoming";
  const topics = topic_ids.length;

  return (
    <li className="hover:bg-subtle flex items-center gap-3 py-3 pr-2 pl-4 transition-colors sm:pl-5">
      <Badge variant="secondary" className="hidden w-24 shrink-0 sm:inline-flex">
        {KIND_LABELS[kind]}
      </Badge>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "truncate font-medium",
            done && "text-muted",
            status === "cancelled" && "line-through",
          )}
        >
          {title}
        </p>
        <p className="text-muted mt-0.5 flex flex-wrap items-center gap-x-3 text-xs">
          <span className="sm:hidden">{KIND_LABELS[kind]}</span>
          <span className="inline-flex items-center gap-1">
            <CalendarClock className="size-3.5" aria-hidden />
            {due_at ? (
              <>
                {formatDue(due_at)} · {relativeDay(due_at)}
              </>
            ) : (
              "No date yet"
            )}
          </span>
          <span>{topics === 0 ? "No topics" : `${topics} topic${topics === 1 ? "" : "s"}`}</span>
          {done && (
            <span className={cn("font-semibold", status === "completed" && "text-success")}>
              {STATUS_LABELS[status]}
            </span>
          )}
        </p>
      </div>
      <span
        className={cn(
          "w-12 shrink-0 text-right text-sm font-semibold tabular-nums",
          done && "text-muted",
        )}
      >
        {weight !== null ? `${weight}%` : "—"}
      </span>
      <div className="flex shrink-0">
        <Button variant="ghost" size="icon-sm" aria-label={`Edit: ${title}`} onClick={onEdit}>
          <Pencil aria-hidden />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete: ${title}`} onClick={onDelete}>
          <Trash2 aria-hidden />
        </Button>
      </div>
    </li>
  );
}
