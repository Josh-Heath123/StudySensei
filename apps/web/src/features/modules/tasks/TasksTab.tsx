import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { formatDue, isPast, relativeDay } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/ui/dialog";
import { NativeSelect } from "@/ui/native-select";

import { useAssessments } from "../assessments/api";
import {
  TASK_STATUS_LABELS,
  useCreateTask,
  useDeleteTask,
  useTasks,
  useUpdateTask,
  type Task,
  type TaskStatus,
} from "./api";
import { TaskForm } from "./TaskForm";

export function TasksTab({ moduleId }: { moduleId: string }) {
  const tasks = useTasks(moduleId);
  const assessments = useAssessments(moduleId);
  const create = useCreateTask(moduleId);
  const update = useUpdateTask();
  const remove = useDeleteTask();
  const [showDone, setShowDone] = useState(false);
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const [toDelete, setToDelete] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);

  const all = tasks.data ?? [];
  const doneCount = all.filter((t) => t.status === "done").length;
  const visible = showDone ? all : all.filter((t) => t.status !== "done");
  const assessmentTitle = new Map((assessments.data ?? []).map((a) => [a.id, a.title]));

  function setStatus(task: Task, status: TaskStatus) {
    setError(null);
    update
      .mutateAsync({ id: task.id, changes: { status } })
      .catch((err: Error) => setError(err.message));
  }

  return (
    <section aria-labelledby="tasks-heading" className="max-w-3xl">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 id="tasks-heading" className="text-lg font-semibold tracking-tight">
            Tasks
          </h2>
          <p className="text-muted-foreground text-sm">
            {all.length - doneCount} open · {doneCount} done
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showDone}
              onChange={(e) => setShowDone(e.target.checked)}
              className="accent-primary size-4"
            />
            Show done
          </label>
          <Button onClick={() => setEditing("new")}>
            <Plus aria-hidden /> Add task
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-destructive mb-3 text-sm">
          {error}
        </p>
      )}
      {tasks.isPending && <p className="text-muted-foreground text-sm">Loading…</p>}
      {tasks.isError && (
        <p role="alert" className="text-destructive text-sm">
          Couldn't load tasks: {tasks.error.message}
        </p>
      )}
      {tasks.data && visible.length === 0 && (
        <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
          {all.length === 0
            ? "No tasks yet. Break assignments into steps you can tick off."
            : "Everything here is done."}
        </p>
      )}

      {visible.length > 0 && (
        <ul aria-label="Tasks" className="divide-y rounded-lg border">
          {visible.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              assessmentTitle={
                task.assessment_id ? assessmentTitle.get(task.assessment_id) : undefined
              }
              onStatus={(status) => setStatus(task, status)}
              onEdit={() => setEditing(task)}
              onDelete={() => setToDelete(task)}
            />
          ))}
        </ul>
      )}

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "Add task" : "Edit task"}</DialogTitle>
          </DialogHeader>
          {editing !== null && (
            <TaskForm
              initial={editing === "new" ? undefined : editing}
              assessments={assessments.data ?? []}
              submitLabel={editing === "new" ? "Add task" : "Save changes"}
              onCancel={() => setEditing(null)}
              onSubmit={async (values) => {
                if (editing === "new") await create.mutateAsync({ ...values, status: "todo" });
                else await update.mutateAsync({ id: editing.id, changes: values });
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
        description="This can't be undone."
        confirmLabel="Delete task"
        onConfirm={() => remove.mutateAsync(toDelete!.id)}
      />
    </section>
  );
}

function TaskRow({
  task,
  assessmentTitle,
  onStatus,
  onEdit,
  onDelete,
}: {
  task: Task;
  assessmentTitle?: string;
  onStatus: (status: TaskStatus) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const done = task.status === "done";
  const overdue = !done && task.due_at !== null && isPast(task.due_at);

  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <input
        type="checkbox"
        aria-label={`Done: ${task.title}`}
        checked={done}
        onChange={(e) => onStatus(e.target.checked ? "done" : "todo")}
        className="accent-primary size-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "truncate text-sm font-medium",
            done && "text-muted-foreground line-through",
          )}
        >
          {task.title}
        </p>
        <p className="text-muted-foreground flex flex-wrap gap-x-3 text-xs">
          {task.due_at && (
            <span className={cn(overdue && "text-destructive font-medium")}>
              {overdue && "Overdue · "}
              {formatDue(task.due_at)} · {relativeDay(task.due_at)}
            </span>
          )}
          {assessmentTitle && <span>For {assessmentTitle}</span>}
        </p>
      </div>
      <NativeSelect
        aria-label={`Status: ${task.title}`}
        value={task.status}
        onChange={(e) => onStatus(e.target.value as TaskStatus)}
        className="h-8 w-32 shrink-0"
      >
        {Object.entries(TASK_STATUS_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </NativeSelect>
      <div className="flex shrink-0">
        <Button variant="ghost" size="icon-sm" aria-label={`Edit: ${task.title}`} onClick={onEdit}>
          <Pencil aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Delete: ${task.title}`}
          onClick={onDelete}
        >
          <Trash2 aria-hidden />
        </Button>
      </div>
    </li>
  );
}
