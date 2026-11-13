import type * as React from "react";

import { cn } from "@/lib/utils";

import { FIELD_CLASS } from "./field";

/** A styled native <select>: accessible and keyboard-friendly by default. */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(FIELD_CLASS, "min-h-11", className)}
      {...props}
    />
  );
}

export { NativeSelect };
