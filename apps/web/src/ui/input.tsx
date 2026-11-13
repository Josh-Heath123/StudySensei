import type * as React from "react";

import { cn } from "@/lib/utils";

import { FIELD_CLASS } from "./field";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(FIELD_CLASS, "min-h-11 py-2", className)}
      {...props}
    />
  );
}

export { Input };
