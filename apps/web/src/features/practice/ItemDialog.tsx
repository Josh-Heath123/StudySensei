import { useId, useState, type FormEvent } from "react";

import { useModules, useTopicTree } from "@/features/modules/api";
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
import { Textarea } from "@/ui/textarea";

import { useCreateItem, useUpdateItem, type ItemKind, type PracticeItem } from "./api";
import { flattenTopics, keyPointLines } from "./practiceText";

/**
 * "Add a card" (the student's own: a flashcard, or a short-answer question with 1 to 5 key
 * points) or editing one. Editing an AI item's text makes it the student's (decision 0009).
 */
export function ItemDialog({
  item,
  moduleId: initialModule,
  topicId: initialTopic,
  onClose,
  onSaved,
}: {
  /** Editing this item; otherwise a new one. */
  item?: PracticeItem;
  moduleId?: string;
  topicId?: string;
  onClose: () => void;
  onSaved?: (message: string) => void;
}) {
  const modules = useModules();
  const [moduleId, setModuleId] = useState(item?.module_id ?? initialModule ?? "");
  const [topicId, setTopicId] = useState(item?.topic_id ?? initialTopic ?? "");
  const [kind, setKind] = useState<ItemKind>(item?.kind ?? "flashcard");
  const [prompt, setPrompt] = useState(item?.prompt ?? "");
  const [answer, setAnswer] = useState(item?.answer ?? "");
  const [keyPoints, setKeyPoints] = useState((item?.key_points ?? []).join("\n"));
  const create = useCreateItem();
  const update = useUpdateItem();
  const save = item ? update : create;
  const id = useId();
  const short = kind === "short_answer";
  const points = keyPointLines(keyPoints);
  const chosenModule = moduleId || modules.data?.[0]?.id || "";
  const tree = useTopicTree(chosenModule);
  const ready =
    chosenModule !== "" &&
    prompt.trim() !== "" &&
    answer.trim() !== "" &&
    (!short || (points.length >= 1 && points.length <= 5));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    const text = {
      prompt: prompt.trim(),
      answer: answer.trim(),
      key_points: short ? points : null,
    };
    try {
      if (item) {
        await update.mutateAsync({ itemId: item.id, ...text, topic_id: topicId || null });
        onSaved?.("Card saved.");
      } else {
        await create.mutateAsync({
          module_id: chosenModule,
          topic_id: topicId || null,
          kind,
          ...text,
        });
        onSaved?.("Card added. It's new, so it shows up in today's reviews.");
      }
      onClose();
    } catch {
      // Shown in the dialog.
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{item ? "Edit card" : "Add a card"}</DialogTitle>
          <DialogDescription>
            {item?.origin === "ai"
              ? "Changing its text makes it yours; its sources stay."
              : "Your own card, in your words. It's scheduled like any other."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="grid gap-4">
          {!item && (
            <div className="grid gap-1.5">
              <Label htmlFor={`${id}-module`}>Module</Label>
              <NativeSelect
                id={`${id}-module`}
                value={chosenModule}
                onChange={(event) => {
                  setModuleId(event.target.value);
                  setTopicId("");
                }}
              >
                {modules.data?.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.code} {m.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-topic`}>Topic</Label>
            <NativeSelect
              id={`${id}-topic`}
              value={topicId}
              onChange={(event) => setTopicId(event.target.value)}
            >
              <option value="">No topic</option>
              {flattenTopics(tree.data ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {" ".repeat(t.depth * 2)}
                  {t.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          {!item && (
            <fieldset className="grid gap-1.5">
              <legend className="mb-1.5 text-sm font-semibold">Kind</legend>
              <div className="bg-subtle grid grid-cols-2 gap-1 rounded-[12px] p-1">
                {(
                  [
                    ["flashcard", "Flashcard"],
                    ["short_answer", "Short answer"],
                  ] as const
                ).map(([value, label]) => (
                  <label
                    key={value}
                    className="text-muted hover:text-fg has-checked:bg-surface has-checked:text-fg has-focus-visible:outline-ring flex min-h-10 cursor-pointer items-center justify-center rounded-[9px] text-sm font-semibold has-checked:shadow-sm has-focus-visible:outline-2 has-focus-visible:-outline-offset-2"
                  >
                    <input
                      type="radio"
                      name={`${id}-kind`}
                      className="sr-only"
                      checked={kind === value}
                      onChange={() => setKind(value)}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-prompt`}>{short ? "Question" : "Front"}</Label>
            <Textarea
              id={`${id}-prompt`}
              rows={2}
              maxLength={500}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-answer`}>{short ? "Reference answer" : "Back"}</Label>
            <Textarea
              id={`${id}-answer`}
              rows={3}
              maxLength={1500}
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
            />
          </div>
          {short && (
            <div className="grid gap-1.5">
              <Label htmlFor={`${id}-points`}>Key points, one per line (1 to 5)</Label>
              <Textarea
                id={`${id}-points`}
                rows={4}
                value={keyPoints}
                aria-describedby={`${id}-points-help`}
                onChange={(event) => setKeyPoints(event.target.value)}
              />
              <p id={`${id}-points-help`} className="text-muted text-xs">
                What a full answer must contain. Marking checks each one, by you or the AI.
              </p>
            </div>
          )}
          {save.isError && (
            <p role="alert" className="text-danger text-sm">
              {save.error.message}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || save.isPending}>
              {save.isPending ? "Saving…" : item ? "Save" : "Add card"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
