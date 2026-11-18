import { useState, type FormEvent } from "react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";

import { useMergeTopicInto, type TopicNode } from "./api";
import { mergeTargets } from "./topicReview";

/** "Merge into": pick the topic that takes over this one's subtopics and pages. */
export function MergeTopicDialog({
  moduleId,
  topic,
  tree,
  onClose,
}: {
  moduleId: string;
  topic: TopicNode;
  tree: TopicNode[];
  onClose: () => void;
}) {
  const merge = useMergeTopicInto(moduleId);
  const choices = mergeTargets(tree, topic.id);
  const [target, setTarget] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!target) return;
    try {
      await merge.mutateAsync({ topicId: topic.id, targetId: target });
      onClose();
    } catch {
      // Shown below.
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Merge “{topic.name}” into…</DialogTitle>
            <DialogDescription>
              Its subtopics and pages move to the topic you pick, then it's removed.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="merge-target">Merge into</Label>
            <NativeSelect
              id="merge-target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Choose a topic</option>
              {choices.map((choice) => (
                <option key={choice.id} value={choice.id}>
                  {`${"  ".repeat(choice.depth)}${choice.name}`}
                </option>
              ))}
            </NativeSelect>
          </div>
          {merge.isError && (
            <p role="alert" className="text-danger text-sm">
              {merge.error.message}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!target || merge.isPending}>
              Merge
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
