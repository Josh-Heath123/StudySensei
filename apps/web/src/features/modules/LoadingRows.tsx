import { cn } from "@/lib/utils";

/**
 * A list that's still loading (docs/DESIGN.md "Skeleton"): a few pulsing rows instead of
 * plain text. Screen readers hear `label` once, through a polite status.
 */
export function LoadingRows({
  label = "Loading…",
  rows = 3,
  className,
  rowClassName = "h-14",
}: {
  label?: string;
  rows?: number;
  className?: string;
  rowClassName?: string;
}) {
  return (
    <div role="status" className={cn("grid gap-2", className)}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} aria-hidden className={cn("skeleton", rowClassName)} />
      ))}
    </div>
  );
}
