import { useState, type FormEvent } from "react";

import { fromIso, toIso } from "@/lib/dates";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";
import { Textarea } from "@/ui/textarea";

import { useTopicTree, type TopicNode } from "../api";
import {
  DEFAULT_TIME,
  KIND_LABELS,
  STATUS_LABELS,
  type Assessment,
  type AssessmentInput,
  type AssessmentKind,
  type AssessmentStatus,
} from "./api";

type Props = {
  moduleId: string;
  initial?: Assessment;
  submitLabel: string;
  onSubmit: (values: AssessmentInput & { status: AssessmentStatus }) => Promise<unknown>;
  onCancel: () => void;
};

function flatten(nodes: TopicNode[], depth = 0): { topic: TopicNode; depth: number }[] {
  return nodes.flatMap((topic) => [{ topic, depth }, ...flatten(topic.children, depth + 1)]);
}

export function AssessmentForm({ moduleId, initial, submitLabel, onSubmit, onCancel }: Props) {
  const tree = useTopicTree(moduleId);
  const due = initial?.due_at ? fromIso(initial.due_at) : null;

  const [title, setTitle] = useState(initial?.title ?? "");
  const [kind, setKind] = useState<AssessmentKind>(initial?.kind ?? "exam");
  const [date, setDate] = useState(due?.date ?? "");
  const [time, setTime] = useState(due?.time ?? DEFAULT_TIME[initial?.kind ?? "exam"]);
  const [timeTouched, setTimeTouched] = useState(Boolean(due));
  const [weight, setWeight] = useState(initial?.weight?.toString() ?? "");
  const [status, setStatus] = useState<AssessmentStatus>(initial?.status ?? "upcoming");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [topicIds, setTopicIds] = useState(new Set(initial?.topic_ids ?? []));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function changeKind(next: AssessmentKind) {
    setKind(next);
    // Follow the kind's usual time until the user picks one themselves.
    if (!timeTouched) setTime(DEFAULT_TIME[next]);
  }

  function toggleTopic(id: string, checked: boolean) {
    setTopicIds((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        kind,
        due_at: date ? toIso(date, time) : null,
        weight: weight === "" ? null : Number(weight),
        status,
        notes: notes.trim() || null,
        topic_ids: [...topicIds],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  const topics = flatten(tree.data ?? []);

  return (
    <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
      <div className="grid grid-cols-[1fr_10rem] gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="assessment-title">Title</Label>
          <Input
            id="assessment-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Semester test 1"
            maxLength={200}
            required
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="assessment-kind">Kind</Label>
          <NativeSelect
            id="assessment-kind"
            value={kind}
            onChange={(e) => changeKind(e.target.value as AssessmentKind)}
          >
            {Object.entries(KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="assessment-date">Date</Label>
          <Input
            id="assessment-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="assessment-time">Time</Label>
          <Input
            id="assessment-time"
            type="time"
            value={time}
            disabled={!date}
            onChange={(e) => {
              setTime(e.target.value);
              setTimeTouched(true);
            }}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="assessment-weight">Weight (%)</Label>
          <Input
            id="assessment-weight"
            type="number"
            inputMode="decimal"
            min={0}
            max={100}
            step={0.5}
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            placeholder="e.g. 40"
          />
        </div>
      </div>

      {initial && (
        <div className="grid gap-1.5">
          <Label htmlFor="assessment-status">Status</Label>
          <NativeSelect
            id="assessment-status"
            value={status}
            onChange={(e) => setStatus(e.target.value as AssessmentStatus)}
          >
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}

      <fieldset className="grid gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">Topics it covers</legend>
        {tree.isPending && <p className="text-muted text-sm">Loading topics…</p>}
        {tree.data && topics.length === 0 && (
          <p className="text-muted text-sm">
            This module has no topics yet. Add them on the Topics tab.
          </p>
        )}
        {topics.length > 0 && (
          <ul className="max-h-48 overflow-y-auto rounded-md border p-2">
            {topics.map(({ topic, depth }) => (
              <li key={topic.id} style={{ paddingLeft: `${depth * 1.25}rem` }}>
                <label className="flex items-center gap-2 py-0.5 text-sm">
                  <input
                    type="checkbox"
                    checked={topicIds.has(topic.id)}
                    onChange={(e) => toggleTopic(topic.id, e.target.checked)}
                    className="accent-ink size-5 cursor-pointer"
                  />
                  {topic.name}
                </label>
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      <div className="grid gap-1.5">
        <Label htmlFor="assessment-notes">
          Notes <span className="text-muted font-normal">(optional)</span>
        </Label>
        <Textarea
          id="assessment-notes"
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
