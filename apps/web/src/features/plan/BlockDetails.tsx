import { Play } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { useSession } from "@/features/session/session";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";

import { useSkipBlock, type PlanBlock } from "./api";
import { MoveDialog } from "./MoveDialog";
import { blockName, measuredText } from "./planText";
import { clock, dayLabel, zoned, type Span } from "./week";

type Props = {
  block: PlanBlock;
  timeZone: string;
  /** The week's dates and their free spans, for Move… (from GET /availability). */
  week: string[];
  freeByDate: Record<string, Span[]>;
  onDone?: () => void;
};

/**
 * What's inside a block's popover or sheet: when, Why (its reason), How (its method), whether
 * the student moved it or it's kept for the next 24 h, and the actions the server allows.
 */
export function BlockDetails({ block, timeZone, week, freeByDate, onDone }: Props) {
  const controller = useSession();
  const navigate = useNavigate();
  const skip = useSkipBlock();
  const [confirmSkip, setConfirmSkip] = useState(false);
  const [moving, setMoving] = useState(false);
  const start = zoned(block.start, timeZone);
  const end = zoned(block.end, timeZone);
  const measured = measuredText(block);

  function startSession() {
    void controller.start({
      moduleId: block.module_id,
      topicId: block.topic_id,
      planBlockId: block.id,
    });
    onDone?.();
    void navigate("/session");
  }

  return (
    <div className="grid gap-4">
      <p className="text-muted text-sm tabular-nums">
        {dayLabel(start.date)}, {clock(start.minutes)}–{clock(end.minutes)} · {block.module_code}{" "}
        {block.assessment_title}
        {block.status !== "planned" && (
          <>
            {" "}
            · <span className="text-fg font-medium capitalize">{block.status}</span>
          </>
        )}
        {measured && <> · {measured}</>}
      </p>
      <div className="grid gap-1">
        <h3 className="type-label text-muted">Why</h3>
        <p className="text-sm">{block.reason_text}</p>
      </div>
      <div className="grid gap-1">
        <h3 className="type-label text-muted">How</h3>
        <p className="text-sm">{block.method_text}</p>
      </div>
      {block.pinned && <p className="text-muted text-xs">Moved by you.</p>}
      {block.fixed && !block.pinned && (
        <p className="text-muted text-xs">Kept for the next 24 h.</p>
      )}
      {(block.actions.start || block.actions.skip || block.actions.move) && (
        <div className="flex flex-wrap gap-2">
          {block.actions.start && (
            <Button variant="module" size="sm" onClick={startSession}>
              <Play aria-hidden /> Start session
            </Button>
          )}
          {block.actions.move && (
            <Button variant="outline" size="sm" onClick={() => setMoving(true)}>
              Move…
            </Button>
          )}
          {block.actions.skip && (
            <Button variant="ghost" size="sm" onClick={() => setConfirmSkip(true)}>
              Skip
            </Button>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirmSkip}
        onOpenChange={setConfirmSkip}
        title="Skip this block?"
        description={`${blockName(block)} on ${dayLabel(start.date)} at ${clock(start.minutes)}. Its time is placed again if there's room.`}
        confirmLabel="Skip"
        busyLabel="Skipping…"
        onConfirm={async () => {
          await skip.mutateAsync(block.id);
          onDone?.();
        }}
      />
      {moving && (
        <MoveDialog
          block={block}
          timeZone={timeZone}
          week={week}
          freeByDate={freeByDate}
          onClose={(moved) => {
            setMoving(false);
            if (moved) onDone?.();
          }}
        />
      )}
    </div>
  );
}
