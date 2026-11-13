import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// Square status chips. Colour never carries meaning alone: the text always says it.
const badgeVariants = cva(
  "inline-flex items-center justify-center gap-1 rounded-sm border px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-ink bg-ink text-paper",
        secondary: "border-line bg-surface text-ink",
        success: "border-success text-success bg-paper",
        warning: "border-warning text-warning bg-paper",
        destructive: "border-danger text-danger bg-paper",
        outline: "border-ink text-ink bg-paper",
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
