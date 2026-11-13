import { useState, type FormEvent } from "react";

import { fromIso, toIso } from "@/lib/dates";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";
import { Textarea } from "@/ui/textarea";

import type { Assessment } from "../assessments/api";
import type { Task, TaskInput } from "./api";

/** What the form edits: everything but status, which the task list changes directly. */
export type TaskFields = Omit<TaskInput, "status">;

type Props = {
  initial?: Task;
  assessments: Assessment[];
  submitLabel: string;
  onSubmit: (values: TaskFields) => Promise<unknown>;
  onCancel: () => void;
};

export function TaskForm({ initial, assessments, submitLabel, onSubmit, onCancel }: Props) {
  const due = initial?.due_at ? fromIso(initial.due_at) : null;
  const [title, setTitle] = useState(initial?.title ?? "");
  const [date, setDate] = useState(due?.date ?? "");
  const [time, setTime] = useState(due?.time ?? "23:59");
  const [assessmentId, setAssessmentId] = useState(initial?.assessment_id ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        assessment_id: assessmentId || null,
        due_at: date ? toIso(date, time) : null,
        notes: notes.trim() || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
      <div className="grid gap-1.5">
        <Label htmlFor="task-title">Task</Label>
        <Input
          id="task-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Write up the architecture decision record"
          maxLength={200}
          required
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="task-date">Due date</Label>
          <Input
            id="task-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="task-time">Time</Label>
          <Input
            id="task-time"
            type="time"
            value={time}
            disabled={!date}
            onChange={(e) => setTime(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="task-assessment">For assessment</Label>
        <NativeSelect
          id="task-assessment"
          value={assessmentId}
          onChange={(e) => setAssessmentId(e.target.value)}
        >
          <option value="">None</option>
          {assessments.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title}
            </option>
          ))}
        </NativeSelect>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="task-notes">
          Notes <span className="text-muted font-normal">(optional)</span>
        </Label>
        <Textarea
          id="task-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
        />
      </div>

      {error && (
        <p role="alert" className="text-danger text-sm">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving || !title.trim()}>
          {saving ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
