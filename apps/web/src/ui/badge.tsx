import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// Small status chips. Colour never carries meaning alone: the text always says it.
const badgeVariants = cva(
  "inline-flex items-center justify-center gap-1 rounded-sm border px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-transparent bg-accent-soft text-fg",
        secondary: "border-transparent bg-subtle text-muted",
        success: "border-success/35 text-success bg-surface",
        warning: "border-warning/35 text-warning bg-surface",
        destructive: "border-danger/35 text-danger bg-surface",
        outline: "border-line-strong text-fg bg-surface",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span";
  return (
    <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
