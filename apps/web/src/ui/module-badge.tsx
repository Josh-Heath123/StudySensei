import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A module's code on its own colour (docs/DESIGN.md "Module badge"). Module colours
 * are always fills behind dark text. Without `colour`, it uses the page's `--module`.
 */
function ModuleBadge({
  colour,
  className,
  style,
  ...props
}: React.ComponentProps<"span"> & { colour?: string }) {
  return (
    <span
      data-slot="module-badge"
      className={cn(
        "text-on-fill inline-flex items-center rounded-sm px-2 py-1 text-xs leading-none font-semibold whitespace-nowrap",
        !colour && "bg-[var(--module)]",
        className,
      )}
      style={colour ? { backgroundColor: colour, ...style } : style}
      {...props}
    />
  );
}

export { ModuleBadge };
