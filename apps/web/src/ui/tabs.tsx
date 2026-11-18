import { Tabs as TabsPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// docs/DESIGN.md "Tabs": a segmented control. The track is the subtle fill; the selected
// segment is a raised solid surface. It scrolls sideways on narrow screens. Radix supplies
// role="tab" and aria-selected.

function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  );
}

function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "bg-subtle flex w-full [scrollbar-width:none] gap-1 overflow-x-auto rounded-[12px] p-1",
        className,
      )}
      {...props}
    />
  );
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "text-muted hover:text-fg inline-flex min-h-10 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-[9px] px-3 py-2 text-sm font-semibold whitespace-nowrap transition-[background-color,color,box-shadow] focus-visible:-outline-offset-2 disabled:pointer-events-none disabled:opacity-45",
        "data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-sm",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 outline-none", className)}
      {...props}
    />
  );
}

export { Tabs, TabsContent, TabsList, TabsTrigger };
