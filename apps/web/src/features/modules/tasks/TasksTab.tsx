import { CircleCheck, ListTodo, Pencil, Plus, Trash2 } from "lucide-react";
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
import { EmptyState } from "../EmptyState";
import { LoadingRows } from "../LoadingRows";
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
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h2 id="tasks-heading" className="type-h2 mb-1">
            Tasks
          </h2>
          <p className="text-muted tabular text-sm">
            {all.length - doneCount} open · {doneCount} done
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="hover:bg-subtle flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-2 text-sm font-medium transition-colors">
            <input
              type="checkbox"
              checked={showDone}
              onChange={(e) => setShowDone(e.target.checked)}
              className="accent-primary size-5 cursor-pointer"
            />
            Show done
          </label>
          <Button variant="outline" onClick={() => setEditing("new")}>
            <Plus aria-hidden /> Add task
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-danger mb-3 text-sm">
          {error}
        </p>
      )}
      {tasks.isPending && <LoadingRows label="Loading tasks…" />}
      {tasks.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load tasks: {tasks.error.message}
        </p>
      )}
      {tasks.data && visible.length === 0 && (
        <EmptyState icon={all.length === 0 ? ListTodo : CircleCheck}>
          {all.length === 0
            ? "No tasks yet. Break assignments into steps you can tick off."
            : "Everything here is done."}
        </EmptyState>
      )}

      {visible.length > 0 && (
        <ul
          aria-label="Tasks"
          className="surface-card divide-line divide-y overflow-hidden rounded-xl"
        >
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
    <li className="hover:bg-subtle flex flex-wrap items-center gap-x-3 gap-y-2 py-3 pr-2 pl-4 transition-colors sm:pl-5">
      <input
        type="checkbox"
        aria-label={`Done: ${task.title}`}
        checked={done}
        onChange={(e) => onStatus(e.target.checked ? "done" : "todo")}
        className="accent-primary size-5 shrink-0 cursor-pointer"
      />
      <div className="min-w-[10rem] flex-1">
        <p className={cn("truncate text-sm font-medium", done && "text-muted line-through")}>
          {task.title}
        </p>
        <p className="text-muted mt-0.5 flex flex-wrap gap-x-3 text-xs">
          {task.due_at && (
            <span className={cn(overdue && "text-danger font-medium")}>
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
        className="ml-8 w-36 shrink-0 sm:ml-0"
      >
        {Object.entries(TASK_STATUS_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </NativeSelect>
      <div className="ml-auto flex shrink-0">
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
