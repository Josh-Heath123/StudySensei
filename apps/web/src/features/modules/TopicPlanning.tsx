import { useId, useState, type FormEvent } from "react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { useTopicMastery, useTopicPlanning, type TopicNode } from "./api";
import { BAND_LABELS, BAND_VARIANTS } from "./masteryText";
import { CONFIDENCE_LABELS, subtreeWorkloadText, workloadText } from "./planningText";

const RATINGS = [null, 1, 2, 3, 4, 5] as const;

/**
 * In a topic's detail: how sure the student is to start with (self-rated, 1 to 5) and how
 * long it takes (estimated from its pages, or their own figure).
 */
export function TopicPlanning({ moduleId, topic }: { moduleId: string; topic: TopicNode }) {
  const save = useTopicPlanning(moduleId, topic.id);
  const name = useId();
  const [editing, setEditing] = useState(false);
  const confidence = topic.confidence ?? null;
  const { workload } = topic;
  // A chapter: what the planner counts when it's ticked in an assessment (decision 0019).
  const whole = topic.workload_with_subtopics ?? null;

  return (
    <section aria-label="Planning" className="surface-card grid gap-4 rounded-lg p-4">
      <fieldset className="grid gap-2">
        <legend className="type-label mb-2">Starting confidence</legend>
        <div className="bg-subtle grid grid-cols-6 gap-1 rounded-[12px] p-1">
          {RATINGS.map((rating) => (
            <label
              key={rating ?? "none"}
              title={rating ? CONFIDENCE_LABELS[rating] : "Not rated yet"}
              className="text-muted hover:text-fg has-checked:bg-surface has-checked:text-fg has-focus-visible:outline-ring flex min-h-10 cursor-pointer items-center justify-center rounded-[9px] px-1 text-sm font-semibold transition-[background-color,color,box-shadow] has-checked:shadow-sm has-focus-visible:outline-2 has-focus-visible:-outline-offset-2"
            >
              <input
                type="radio"
                name={name}
                className="sr-only"
                checked={confidence === rating}
                disabled={save.isPending}
                onChange={() => save.mutate({ confidence: rating })}
                aria-label={rating ? `${rating}: ${CONFIDENCE_LABELS[rating]}` : "Not rated"}
              />
              {rating ?? "–"}
            </label>
          ))}
        </div>
        <p className="text-muted text-xs">
          {confidence
            ? `${confidence}/5: ${CONFIDENCE_LABELS[confidence]}. Your own rating.`
            : "Not rated. 1 is new to you, 5 is you could teach it."}
        </p>
        <MasteryLine moduleId={moduleId} topicId={topic.id} />
      </fieldset>

      <div className="grid gap-2">
        <h3 className="type-label">Workload</h3>
        {editing ? (
          <WorkloadForm
            initial={workload.minutes}
            onCancel={() => setEditing(false)}
            onSave={async (minutes) => {
              await save.mutateAsync({ estimated_minutes: minutes });
              setEditing(false);
            }}
          />
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="text-sm">{workloadText(workload)}</p>
            <Button variant="quiet" size="sm" onClick={() => setEditing(true)}>
              {workload.source === "yours" ? "Change" : "Set your own"}
            </Button>
            {workload.source === "yours" && (
              <Button
                variant="quiet"
                size="sm"
                disabled={save.isPending}
                onClick={() => save.mutate({ estimated_minutes: null })}
              >
                Use the estimate
              </Button>
            )}
          </div>
        )}
        {whole && whole.source !== "yours" && !editing && (
          <p className="text-sm">{subtreeWorkloadText(whole)}</p>
        )}
        {(workload.source === "estimated" || whole?.source === "estimated") && !editing && (
          <p className="text-muted text-xs">
            Estimated at 3 minutes a slide and 6 a page of notes.
          </p>
        )}
        {whole && (
          <p className="text-muted text-xs">
            A figure you set here covers the whole chapter, subtopics included, when it&apos;s in an
            assessment.
          </p>
        )}
      </div>
      {save.isError && (
        <p role="alert" className="text-danger text-sm">
          {save.error.message}
        </p>
      )}
    </section>
  );
}

/** Read-only: the band and what it rests on, or why there isn't one yet (ADRs 0027, 0028). */
function MasteryLine({ moduleId, topicId }: { moduleId: string; topicId: string }) {
  const { data } = useTopicMastery(moduleId, topicId);
  if (!data) return null;
  return (
    <p
      aria-label="Mastery"
      className="text-muted flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs"
    >
      {data.band && <Badge variant={BAND_VARIANTS[data.band]}>{BAND_LABELS[data.band]}</Badge>}
      <span>{data.basis}</span>
    </p>
  );
}

function WorkloadForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: number | null;
  onSave: (minutes: number) => Promise<void>;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial === null ? "" : String(initial));
  const minutes = Number(value);
  const valid = value !== "" && Number.isInteger(minutes) && minutes >= 5 && minutes <= 6000;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (valid) onSave(minutes).catch(() => {});
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <Input
        type="number"
        inputMode="numeric"
        min={5}
        max={6000}
        step={5}
        autoFocus
        aria-label="Your workload, in minutes"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && onCancel()}
        className="w-28"
      />
      <span className="text-muted text-sm">minutes</span>
      <Button type="submit" size="sm" disabled={!valid}>
        Save
      </Button>
      <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}
