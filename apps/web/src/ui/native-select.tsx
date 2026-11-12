import type * as React from "react";

import { cn } from "@/lib/utils";

/** A styled native <select>: accessible and keyboard-friendly by default. */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "border-input bg-background focus-visible:ring-ring/50 h-9 w-full rounded-md border px-3 text-sm shadow-xs focus-visible:ring-[3px] focus-visible:outline-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { NativeSelect };
