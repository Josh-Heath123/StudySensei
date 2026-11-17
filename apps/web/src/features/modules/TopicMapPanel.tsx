import { Eraser, Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";

import { useAiStatus, useBuildTopicMap, useClearAiTopics, useTopicMap } from "./api";
import { describeTopicMap } from "./topicMap";

/**
 * "Build topic map" with honest progress and states (decision 0006), and "Clear AI
 * topics" (decision 0007) for starting the AI's part of the tree again.
 */
export function TopicMapPanel({ moduleId, aiTopics }: { moduleId: string; aiTopics: number }) {
  const status = useTopicMap(moduleId);
  const ai = useAiStatus();
  const build = useBuildTopicMap(moduleId);
  const clear = useClearAiTopics(moduleId);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

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
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setConfirmClear(true)}
          disabled={aiTopics === 0 || view.busy || clear.isPending}
        >
          <Eraser aria-hidden />
          Clear AI topics
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
      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title={`Clear ${aiTopics} AI ${aiTopics === 1 ? "topic" : "topics"}?`}
        description="Every topic still marked AI is deleted. Topics you made or edited stay (any under an AI topic move up). Building again re-uses the analysed materials, so it costs no new analysis."
        confirmLabel="Clear AI topics"
        onConfirm={() => clear.mutateAsync()}
      />
    </div>
  );
}
