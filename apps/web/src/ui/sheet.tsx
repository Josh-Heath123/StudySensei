import * as React from "react";
import { XIcon } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * A bottom sheet (docs/DESIGN.md "Glass": dialogs and sheets): a Radix dialog pinned to the
 * bottom edge, `glass-strong`, radius 24 on its top corners, within the viewport.
 */
function Sheet(props: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetContent({
  className,
  children,
  title,
  description,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & {
  title: string;
  description?: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="bg-scrim data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 fixed inset-0 z-50 duration-200" />
      <DialogPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          "glass-strong text-fg ease-soft fixed inset-x-0 bottom-0 z-50 flex max-h-[88dvh] flex-col rounded-t-2xl pb-[env(safe-area-inset-bottom)] duration-320 outline-none",
          "motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:slide-in-from-bottom motion-safe:data-[state=closed]:animate-out motion-safe:data-[state=closed]:slide-out-to-bottom",
          className,
        )}
        {...props}
      >
        <div className="flex items-center gap-3 px-5 pt-4 pb-2">
          <DialogPrimitive.Title className="type-h3 min-w-0 flex-1">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close className="text-muted hover:text-fg hover:bg-subtle rounded-md p-1.5 transition-colors">
            <XIcon className="size-4" aria-hidden />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        </div>
        {description ? (
          <DialogPrimitive.Description className="sr-only">
            {description}
          </DialogPrimitive.Description>
        ) : (
          <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
        )}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export { Sheet, SheetContent };
