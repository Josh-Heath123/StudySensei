import { MoreHorizontal } from "lucide-react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * docs/DESIGN.md "Menu": a glass popover (`glass-strong`, radius 16) of actions. Radix gives it
 * keyboard support (arrows, Enter, Escape, typeahead) and role="menu" / "menuitem".
 */
function DropdownMenu(props: React.ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root data-slot="dropdown-menu" {...props} />;
}

function DropdownMenuTrigger(props: React.ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  return <DropdownMenuPrimitive.Trigger data-slot="dropdown-menu-trigger" {...props} />;
}

/** The "…" trigger: an icon button whose accessible name says what it's for. */
function MoreButton({
  label,
  className,
  ...props
}: React.ComponentProps<"button"> & { label: string }) {
  return (
    <DropdownMenuPrimitive.Trigger asChild>
      <button
        type="button"
        aria-label={label}
        className={cn(
          "text-muted hover:text-fg hover:bg-subtle data-[state=open]:bg-subtle data-[state=open]:text-fg inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-md transition-colors",
          className,
        )}
        {...props}
      >
        <MoreHorizontal className="size-5" aria-hidden />
      </button>
    </DropdownMenuPrimitive.Trigger>
  );
}

function DropdownMenuContent({
  className,
  sideOffset = 6,
  align = "end",
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        data-slot="dropdown-menu-content"
        sideOffset={sideOffset}
        align={align}
        className={cn(
          "glass-strong text-fg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.97] data-[state=closed]:zoom-out-[0.97] ease-soft z-50 min-w-44 overflow-hidden rounded-lg p-1.5 duration-200",
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

function DropdownMenuItem({
  className,
  destructive = false,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Item> & { destructive?: boolean }) {
  return (
    <DropdownMenuPrimitive.Item
      data-slot="dropdown-menu-item"
      className={cn(
        "flex min-h-10 cursor-pointer items-center gap-2.5 rounded-md px-3 text-sm font-medium outline-none select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0",
        destructive
          ? "text-danger data-[highlighted]:bg-[color-mix(in_srgb,var(--danger)_10%,transparent)]"
          : "data-[highlighted]:bg-subtle",
        className,
      )}
      {...props}
    />
  );
}

function DropdownMenuSeparator({
  className,
  ...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Separator>) {
  return (
    <DropdownMenuPrimitive.Separator
      className={cn("bg-line mx-1 my-1 h-px", className)}
      {...props}
    />
  );
}

export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  MoreButton,
};
