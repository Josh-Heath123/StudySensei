import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { DEFAULT_PLAN } from "@/session-engine/timer";
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

import { useModules, useTopicTree } from "../modules/api";
import { useSession } from "./session";
import { flattenTopics } from "./topics";

type Props = {
  /** Preset on a module's page; on Today the student picks one. */
  moduleId?: string;
  onClose: () => void;
};

export function StartSessionDialog({ moduleId: fixedModuleId, onClose }: Props) {
  const controller = useSession();
  const navigate = useNavigate();
  const modules = useModules();
  const [chosenModuleId, setChosenModuleId] = useState("");
  const [topicId, setTopicId] = useState("");

  const moduleId = fixedModuleId ?? (chosenModuleId || modules.data?.[0]?.id || "");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!moduleId) return;
    // The session opens at once; the server hears about it as soon as it can.
    void controller.start({ moduleId, topicId: topicId || null });
    navigate("/session");
  }

  const noModules = fixedModuleId === undefined && modules.data?.length === 0;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start a study session</DialogTitle>
          <DialogDescription>
            The timer runs {DEFAULT_PLAN.focusMin} minutes of focus, then suggests a{" "}
            {DEFAULT_PLAN.breakMin}-minute break.
          </DialogDescription>
        </DialogHeader>
        {noModules ? (
          <p>
            Add a module first.{" "}
            <Link to="/modules" className="text-link font-semibold underline underline-offset-4">
              Go to modules
            </Link>
          </p>
        ) : (
          <form className="grid gap-5" onSubmit={submit}>
            {fixedModuleId === undefined && (
              <div className="grid gap-2">
                <Label htmlFor="session-module">Module</Label>
                <NativeSelect
                  id="session-module"
                  value={moduleId}
                  disabled={modules.isPending}
                  onChange={(event) => {
                    setChosenModuleId(event.target.value);
                    setTopicId("");
                  }}
                >
                  {modules.data?.map((module) => (
                    <option key={module.id} value={module.id}>
                      {module.code} · {module.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
            {moduleId && <TopicSelect moduleId={moduleId} value={topicId} onChange={setTopicId} />}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="module" disabled={!moduleId}>
                Start
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function TopicSelect({
  moduleId,
  value,
  onChange,
}: {
  moduleId: string;
  value: string;
  onChange: (topicId: string) => void;
}) {
  const tree = useTopicTree(moduleId);
  const topics = flattenTopics(tree.data ?? []);
  return (
    <div className="grid gap-2">
      <Label htmlFor="session-topic">Topic (optional)</Label>
      <NativeSelect
        id="session-topic"
        value={value}
        disabled={tree.isPending}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Whole module</option>
        {topics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {" ".repeat(topic.depth)}
            {topic.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
