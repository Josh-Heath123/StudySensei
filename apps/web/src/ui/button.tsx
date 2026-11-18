import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

// docs/DESIGN.md "Button". One primary (violet) action per screen; everything else is
// secondary (outline), quiet or ghost. `module` and `onDark` are kept as names for their
// call sites: the main action is violet, and nothing sits on an ink card any more.
const primary =
  "bg-primary text-on-primary border border-primary-edge shadow-sm hover:bg-primary-hover";
const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md font-semibold whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform] duration-[120ms] ease-soft select-none active:scale-[0.98] motion-reduce:active:scale-100 disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: primary,
        module: primary,
        outline: "border-line-strong bg-surface text-fg hover:bg-subtle border",
        quiet: "bg-subtle text-fg hover:bg-accent-soft font-medium",
        onDark: "border-line-strong bg-surface text-fg hover:bg-subtle border",
        destructive:
          "border-danger/50 bg-surface text-danger hover:bg-[color-mix(in_srgb,var(--danger)_10%,var(--surface))] border",
        secondary: "bg-subtle text-fg hover:bg-accent-soft",
        ghost: "text-fg hover:bg-subtle",
        link: "text-link underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default: "min-h-11 px-5 py-2.5 text-base",
        sm: "min-h-9 px-3 py-1.5 text-sm",
        lg: "min-h-12 px-6 py-3 text-base",
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
