import { Sparkles } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { Button } from "@/ui/button";

import { practiceKeys, useGenerate, useGenerations } from "./api";
import { generationText } from "./practiceText";

/**
 * "Generate practice" for a topic (ADR 0025): queues the AI to write 8 items from the topic's
 * slides and notes, then follows it (queued, writing, then "8 written" or why not). Only what
 * happens after pressing it here is shown.
 */
export function GenerateButton({ topicId, topicName }: { topicId: string; topicName: string }) {
  const generate = useGenerate(topicId);
  const created = generate.data;
  const generations = useGenerations(topicId, created !== undefined);
  const queryClient = useQueryClient();
  // The one this button queued, as the polled list last saw it.
  const newest = created && (generations.data?.find((g) => g.id === created.id) ?? created);
  const active = newest?.status === "queued" || newest?.status === "running";
  const seen = useRef<string | null>(null);

  // When it finishes, the new items reach the lists, the queue and mastery.
  useEffect(() => {
    if (newest && !active && seen.current !== `${newest.id}-${newest.status}`) {
      seen.current = `${newest.id}-${newest.status}`;
      if (newest.status === "succeeded") {
        void queryClient.invalidateQueries({ queryKey: practiceKeys.all });
        void queryClient.invalidateQueries({ queryKey: ["topics"] });
      }
    }
  }, [newest, active, queryClient]);

  async function start() {
    try {
      await generate.mutateAsync();
    } catch {
      // Shown beside the button.
    }
  }

  const status = generate.isError ? generate.error.message : generationText(newest);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <Button
        variant="quiet"
        size="sm"
        disabled={generate.isPending || active}
        onClick={() => void start()}
        aria-label={`Generate practice for ${topicName}`}
      >
        <Sparkles aria-hidden />
        Generate practice
      </Button>
      <span
        aria-live="polite"
        className={
          newest?.status === "failed" || generate.isError
            ? "text-danger text-sm"
            : "text-muted text-sm"
        }
      >
        {status}
      </span>
    </div>
  );
}
