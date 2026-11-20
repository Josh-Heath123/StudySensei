import { Popover } from "radix-ui";
import type { ReactNode } from "react";

import { useMediaQuery } from "@/lib/useMediaQuery";
import { Sheet, SheetContent } from "@/ui/sheet";

import type { PlanBlock } from "./api";
import { BlockDetails } from "./BlockDetails";
import { blockTitle } from "./planText";
import type { Span } from "./week";

const PHONE_UP = "(min-width: 640px)";

type Props = {
  block: PlanBlock;
  timeZone: string;
  week: string[];
  freeByDate: Record<string, Span[]>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The card that opens it (a button). */
  children: ReactNode;
};

/**
 * docs/DESIGN.md "Block popover": a `glass-strong` popover beside the card from 640 px, and
 * a bottom sheet on phones. The card is the trigger either way.
 */
export function BlockPopover({
  block,
  timeZone,
  week,
  freeByDate,
  open,
  onOpenChange,
  children,
}: Props) {
  const roomy = useMediaQuery(PHONE_UP, true);
  const details = (
    <BlockDetails
      block={block}
      timeZone={timeZone}
      week={week}
      freeByDate={freeByDate}
      onDone={() => onOpenChange(false)}
    />
  );
  if (!roomy) {
    return (
      <>
        <div onClick={() => onOpenChange(true)}>{children}</div>
        <Sheet open={open} onOpenChange={onOpenChange}>
          <SheetContent title={blockTitle(block)}>
            <div className="overflow-y-auto px-5 pb-6">{details}</div>
          </SheetContent>
        </Sheet>
      </>
    );
  }
  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger asChild>{children}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="right"
          align="start"
          sideOffset={8}
          collisionPadding={16}
          aria-label={blockTitle(block)}
          className="glass-strong text-fg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 ease-soft z-50 w-[22rem] max-w-[calc(100vw-2rem)] rounded-xl p-5 duration-200 outline-none"
        >
          <h2 className="type-h3 mb-3">{blockTitle(block)}</h2>
          {details}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
