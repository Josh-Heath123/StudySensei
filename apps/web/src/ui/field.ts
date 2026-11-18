/**
 * Shared look of text inputs, selects and textareas (docs/DESIGN.md "Form fields"): 15 px,
 * a 1 px `line-strong` border (3:1), radius 10, min-height 44, solid (never glass). Focus
 * gives a violet border plus the focus ring.
 */
export const FIELD_CLASS =
  "w-full min-w-0 rounded-md border border-line-strong bg-surface px-3 text-base text-fg outline-none " +
  "transition-[border-color,box-shadow] placeholder:text-muted hover:border-muted " +
  "focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:border-danger";
