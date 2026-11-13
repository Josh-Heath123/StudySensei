import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// docs/DESIGN.md "Button". One loud action per screen: `module` is reserved for it.
const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md font-semibold whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-ink text-paper hover:bg-ink/85",
        module: "text-ink bg-[var(--module)] hover:brightness-95",
        outline: "border-ink bg-paper text-ink hover:bg-surface border-2",
        quiet: "bg-surface text-ink hover:bg-line font-medium",
        onDark: "border-on-dark-line text-paper hover:bg-paper/10 border bg-transparent",
        destructive: "bg-danger text-paper hover:bg-danger/90",
        secondary: "bg-surface text-ink hover:bg-line",
        ghost: "text-ink hover:bg-surface",
        link: "text-ink underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-11 px-[22px] py-3 text-base",
        sm: "min-h-9 px-3 py-1.5 text-sm",
        lg: "min-h-12 px-7 py-3 text-base",
        icon: "size-11",
        "icon-sm": "size-9",
      },
    },
    // Quiet buttons are suggestion chips: 13/500, min-height 36.
    compoundVariants: [{ variant: "quiet", size: "default", class: "min-h-9 px-3 py-1.5 text-sm" }],
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
