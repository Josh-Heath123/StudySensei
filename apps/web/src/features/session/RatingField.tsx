import { cn } from "@/lib/utils";

const RATINGS = [1, 2, 3, 4, 5] as const;

/** A 1–5 rating as a row of radio buttons inside a fieldset (the legend names it). */
export function RatingField({
  legend,
  name,
  value,
  onChange,
  low,
  high,
  invalid = false,
}: {
  legend: string;
  name: string;
  value: number | null;
  onChange: (value: number) => void;
  low: string;
  high: string;
  invalid?: boolean;
}) {
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-sm font-semibold">{legend}</legend>
      <div className="flex gap-2">
        {RATINGS.map((rating) => (
          <label
            key={rating}
            className={cn(
              "has-[:focus-visible]:outline-ring ease-soft flex min-h-11 min-w-11 cursor-pointer items-center justify-center rounded-md border font-semibold tabular-nums transition-[background-color,border-color,color,transform] duration-[120ms] select-none active:scale-[0.98] has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 motion-reduce:active:scale-100",
              value === rating
                ? "border-primary-edge bg-primary text-on-primary shadow-sm"
                : "border-line-strong bg-surface text-fg hover:bg-subtle",
              invalid && value === null && "border-danger",
            )}
          >
            <input
              type="radio"
              name={name}
              value={rating}
              checked={value === rating}
              onChange={() => onChange(rating)}
              className="sr-only"
            />
            {rating}
          </label>
        ))}
      </div>
      <p className="text-muted flex justify-between text-xs">
        <span>1 = {low}</span>
        <span>5 = {high}</span>
      </p>
    </fieldset>
  );
}
