/**
 * Shared look of text inputs, selects and textareas (docs/DESIGN.md "Form fields"):
 * 15 px, 2 px `line` border, radius 4, min-height 44; focus gives a 2 px ink border
 * plus the focus ring.
 */
export const FIELD_CLASS =
  "w-full min-w-0 rounded-md border-2 border-line bg-paper px-3 text-base text-ink outline-none " +
  "placeholder:text-muted focus-visible:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-ink disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger";
