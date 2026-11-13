import type * as React from "react";

import { cn } from "@/lib/utils";

/** A card: paper with a 2 px `line` border, or `ink` for the one key card on a page. */
function Card({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<"div"> & { variant?: "default" | "key" }) {
  return (
    <div
      data-slot="card"
      className={cn(
        "bg-paper text-ink flex flex-col gap-4 rounded-lg border-2 py-5 sm:py-6",
        variant === "key" ? "border-ink" : "border-line",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="card-header" className={cn("grid gap-1 px-5 sm:px-6", className)} {...props} />
  );
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-title" className={cn("type-h3", className)} {...props} />;
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="card-description" className={cn("text-muted text-sm", className)} {...props} />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("px-5 sm:px-6", className)} {...props} />;
}

export { Card, CardContent, CardDescription, CardHeader, CardTitle };
