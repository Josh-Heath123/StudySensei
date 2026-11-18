import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { formatDuration } from "@/session-engine/format";
import { Button } from "@/ui/button";
import { Label } from "@/ui/label";
import { ModuleBadge } from "@/ui/module-badge";
import { Textarea } from "@/ui/textarea";

import { useModule, useTopicTree } from "../modules/api";
import { useSaveReflection, type ReflectionInput } from "./api";
import type { Finished, SessionController } from "./controller";
import { RatingField } from "./RatingField";
import { flattenTopics } from "./topics";

/**
 * The 20-second reflection: focus 1–5, what was covered, and confidence 1–5 for
 * each topic covered. It's the only ground truth for focus, so it stays short.
 */
export function ReflectionForm({
  controller,
  finished,
}: {
  controller: SessionController;
  finished: Finished;
}) {
  const navigate = useNavigate();
  const module = useModule(finished.moduleId);
  const tree = useTopicTree(finished.moduleId);
  const save = useSaveReflection();
  const [focus, setFocus] = useState<number | null>(null);
  const [covered, setCovered] = useState("");
  // Ticked topics and their confidence (null until rated). The session's topic starts ticked.
  const [ratings, setRatings] = useState<Map<string, number | null>>(
    () => new Map(finished.topicId ? [[finished.topicId, null]] : []),
  );
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<ReflectionInput | null>(null);
  const [tried, setTried] = useState(false);

  async function send(body: ReflectionInput) {
    setError(null);
    const sessionId = await controller.sessionIdForReflection();
    if (sessionId === null) {
      setWaiting(body);
      return;
    }
    setWaiting(null);
    save.mutate(
      { sessionId, body },
      {
        onSuccess: () => controller.reflected(),
        onError: (e) => setError(e.message),
      },
    );
  }

  // Started or ended offline: send as soon as the connection is back.
  useEffect(() => {
    if (waiting === null) return;
    const retry = () => void send(waiting);
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setTried(true);
    if (focus === null) {
      setError("Rate your focus from 1 to 5.");
      return;
    }
    // Only topics still in the tree (the session's topic may have been deleted since).
    const rated = [...ratings].filter(([topicId]) => topics.some((t) => t.id === topicId));
    const unrated = rated.some(([, confidence]) => confidence === null);
    if (unrated) {
      setError("Rate your confidence for each topic you ticked.");
      return;
    }
    void send({
      focus_rating: focus,
      covered_notes: covered.trim() || null,
      topic_ratings: rated.map(([topic_id, confidence]) => ({
        topic_id,
        confidence: confidence!,
      })),
    });
  }

  function toggle(topicId: string, on: boolean) {
    setRatings((current) => {
      const next = new Map(current);
      if (on) next.set(topicId, null);
      else next.delete(topicId);
      return next;
    });
  }

  const topics = flattenTopics(tree.data ?? []);

  return (
    <div
      className="mx-auto max-w-[720px] px-4 py-8 sm:px-8 sm:py-12"
      style={{ "--module": module.data?.colour } as CSSProperties}
    >
      <header className="mb-8">
        <p className="type-label text-muted mb-2 flex items-center gap-3">
          {module.data && <ModuleBadge className="normal-case">{module.data.code}</ModuleBadge>}
          Session ended
        </p>
        <h1 className="type-h1">How did it go?</h1>
        <p className="text-muted mt-2">
          Active {formatDuration(finished.activeMs)}, break {formatDuration(finished.breakMs)}.
          Three quick questions, about 20 seconds.
        </p>
      </header>

      <form className="surface-card grid gap-8 rounded-xl p-5 sm:p-6" onSubmit={submit} noValidate>
        <RatingField
          legend="How focused were you?"
          name="focus"
          value={focus}
          onChange={setFocus}
          low="distracted"
          high="deep focus"
          invalid={tried}
        />

        <div className="grid gap-2">
          <Label htmlFor="covered">What I covered</Label>
          <Textarea
            id="covered"
            maxLength={5000}
            value={covered}
            onChange={(event) => setCovered(event.target.value)}
            placeholder="e.g. Layered style, worked through the 2024 exam question"
          />
        </div>

        <fieldset className="grid gap-3">
          <legend className="mb-2 text-sm font-semibold">Topics covered</legend>
          {tree.isPending && <p className="text-muted text-sm">Loading topics…</p>}
          {tree.data && topics.length === 0 && (
            <p className="text-muted text-sm">This module has no topics yet.</p>
          )}
          {topics.map((topic) => {
            const ticked = ratings.has(topic.id);
            return (
              <div key={topic.id} className="grid gap-3" style={{ paddingLeft: topic.depth * 20 }}>
                <label className="flex min-h-11 items-center gap-3">
                  <input
                    type="checkbox"
                    className="accent-primary size-5"
                    checked={ticked}
                    onChange={(event) => toggle(topic.id, event.target.checked)}
                  />
                  {topic.name}
                </label>
                {ticked && (
                  <div className="pl-8">
                    <RatingField
                      legend={`Confidence in ${topic.name}`}
                      name={`confidence-${topic.id}`}
                      value={ratings.get(topic.id) ?? null}
                      onChange={(confidence) =>
                        setRatings((current) => new Map(current).set(topic.id, confidence))
                      }
                      low="lost"
                      high="could teach it"
                      invalid={tried}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>

        {error && (
          <p role="alert" className="text-danger text-sm">
            {error}
          </p>
        )}
        {waiting && (
          <p role="status" className="text-sm">
            Waiting for a connection to save. Your reflection will be sent when you&apos;re back
            online.
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={save.isPending}>
            Save reflection
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              controller.skipReflection();
              navigate("/");
            }}
          >
            Skip
          </Button>
        </div>
      </form>
    </div>
  );
}
