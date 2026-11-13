import type * as React from "react";

import { cn } from "@/lib/utils";

import { FIELD_CLASS } from "./field";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(FIELD_CLASS, "field-sizing-content min-h-20 py-2", className)}
      {...props}
    />
  );
}

export { Textarea };
