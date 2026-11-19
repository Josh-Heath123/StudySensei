import { MessageCircleQuestion, PanelRightClose } from "lucide-react";
import { memo, useState } from "react";

import { DESKTOP, useMediaQuery } from "@/lib/useMediaQuery";
import { Button } from "@/ui/button";
import { Sheet, SheetContent } from "@/ui/sheet";

import { panelOpenAtStart, rememberPanelOpen } from "./storage";
import { TutorPanel } from "./TutorPanel";
import { useTutor } from "./useTutor";
import { useVoice } from "./useVoice";

/**
 * Where the tutor lives in the session (docs/DESIGN.md "Screens: Session"):
 * - from 1024 px, a collapsible panel on the right (collapsed, just "Ask about this
 *   topic…"); the session grid keeps the timer at its comfortable size beside it;
 * - below that, a "Tutor" button that opens a glass bottom sheet.
 * One conversation per study session, kept here so collapsing or closing never stops an
 * answer. Memoised: the session screen re-renders every second for its timer, and none of
 * that reaches the tutor (its props are three IDs).
 */
export const TutorDock = memo(function TutorDock({
  moduleId,
  sessionId,
  topicId,
}: {
  moduleId: string;
  sessionId: string | null;
  topicId: string | null;
}) {
  const tutor = useTutor({ moduleId, sessionId, topicId });
  const desktop = useMediaQuery(DESKTOP, true);
  const [open, setOpen] = useState(panelOpenAtStart);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [justOpened, setJustOpened] = useState(false);
  // Holding Space talks only while the panel (or the sheet) is showing.
  const voice = useVoice(tutor, { spaceToTalk: desktop ? open : sheetOpen });

  function toggle(next: boolean) {
    setOpen(next);
    setJustOpened(next);
    rememberPanelOpen(next);
  }

  if (!desktop) {
    return (
      <>
        <div className="fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <Button
            variant="outline"
            onClick={() => setSheetOpen(true)}
            className="glass-strong shadow-lg"
          >
            <MessageCircleQuestion aria-hidden />
            Tutor
            {tutor.busy && <span className="sr-only">(answering)</span>}
          </Button>
        </div>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent
            title="Tutor"
            description="Ask about this topic. Answers come from your own material."
            className="h-[88dvh]"
          >
            <TutorPanel tutor={tutor} voice={voice} autoFocus />
          </SheetContent>
        </Sheet>
      </>
    );
  }

  if (!open) {
    return (
      <aside aria-label="Tutor" className="sticky top-4 self-start">
        <button
          type="button"
          onClick={() => toggle(true)}
          className="glass text-muted hover:text-fg flex min-h-12 w-full cursor-pointer items-center gap-2 rounded-2xl px-4 text-left text-[15px] shadow-sm transition-colors"
        >
          <MessageCircleQuestion aria-hidden className="text-link size-5 shrink-0" />
          Ask about this topic…
          {tutor.busy && <span className="text-link ml-auto text-xs">Answering…</span>}
        </button>
      </aside>
    );
  }

  return (
    <aside
      aria-label="Tutor"
      className="glass sticky top-4 flex h-[calc(100dvh-8rem)] max-h-[880px] min-h-[480px] min-w-0 flex-col self-start rounded-2xl"
    >
      <div className="flex items-center gap-2 px-5 pt-4 pb-3">
        <h2 className="type-h3 min-w-0 flex-1">Tutor</h2>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => toggle(false)}
          aria-label="Collapse the tutor"
        >
          <PanelRightClose aria-hidden />
        </Button>
      </div>
      <TutorPanel tutor={tutor} voice={voice} autoFocus={justOpened} />
    </aside>
  );
});
