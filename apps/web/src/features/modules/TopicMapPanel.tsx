import { Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";

import { useAiStatus, useBuildTopicMap, useTopicMap } from "./api";
import { describeTopicMap } from "./topicMap";

/** "Build topic map" with honest progress and states (decision 0006). */
export function TopicMapPanel({ moduleId }: { moduleId: string }) {
  const status = useTopicMap(moduleId);
  const ai = useAiStatus();
  const build = useBuildTopicMap(moduleId);
  const [error, setError] = useState<string | null>(null);

  if (status.isPending) return null;
  if (status.isError) {
    return (
      <p role="alert" className="text-danger mb-4 text-sm">
        Couldn't load the topic map's status: {status.error.message}
      </p>
    );
  }

  const view = describeTopicMap(status.data, ai.data?.available);

  async function start() {
    setError(null);
    try {
      await build.mutateAsync();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div
      role="region"
      aria-label="AI topic map"
      className="border-line bg-surface mb-4 rounded-md border p-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-sm" aria-live="polite">
          {view.message}
        </p>
        <Button
          size="sm"
          variant="secondary"
          onClick={start}
          disabled={!view.canBuild || build.isPending}
        >
          <Sparkles aria-hidden />
          {build.isPending ? "Starting…" : "Build topic map"}
        </Button>
      </div>
      {view.progress && (
        <progress
          className="accent-ink mt-2 h-2 w-full"
          aria-label="Materials analysed"
          max={view.progress.total}
          value={view.progress.done}
        />
      )}
      {view.detail && <p className="text-warning mt-2 text-sm">{view.detail}</p>}
      {error && (
        <p role="alert" className="text-danger mt-2 text-sm">
          {error}
        </p>
      )}
    </div>
  );
}
