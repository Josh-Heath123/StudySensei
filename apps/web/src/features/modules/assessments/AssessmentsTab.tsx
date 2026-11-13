import { CalendarClock, Pencil, Plus, Trash2 } from "lucide-react";
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
    <section aria-labelledby="assessments-heading" className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 id="assessments-heading" className="type-h3">
            Assessments
          </h2>
          <p className="text-muted text-sm">
            Exams, tests and assignments, with their dates, weights and the topics they cover.
          </p>
        </div>
        <Button onClick={() => setEditing("new")}>
          <Plus aria-hidden /> Add assessment
        </Button>
      </div>

      {assessments.isPending && <p className="text-muted text-sm">Loading…</p>}
      {assessments.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load assessments: {assessments.error.message}
        </p>
      )}
      {assessments.data?.length === 0 && (
        <p className="text-muted border-line rounded-lg border-2 p-6">
          No assessments yet. Add the module's exams, tests and assignments from the study guide.
        </p>
      )}

      {items.length > 0 && (
        <>
          <ul aria-label="Assessments" className="divide-line border-line divide-y border-y">
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
            <p className="text-muted mt-2 text-right text-sm">
              Weights total <span className="text-ink font-medium">{total}%</span>
              {total !== 100 && " (not 100%)"}
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
    <li className={cn("flex items-center gap-3 py-3", done && "opacity-60")}>
      <Badge variant="secondary" className="w-24 shrink-0">
        {KIND_LABELS[kind]}
      </Badge>
      <div className="min-w-0 flex-1">
        <p className={cn("truncate font-medium", status === "cancelled" && "line-through")}>
          {title}
        </p>
        <p className="text-muted flex flex-wrap items-center gap-x-3 text-xs">
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
          {done && <span>{STATUS_LABELS[status]}</span>}
        </p>
      </div>
      <span className="w-12 text-right text-sm font-medium tabular-nums">
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
