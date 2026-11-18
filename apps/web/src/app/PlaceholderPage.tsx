import { ChartNoAxesColumn, CalendarRange, Layers, Sparkles } from "lucide-react";

import { PageHeader } from "./PageHeader";

const ICONS: Record<string, typeof Sparkles> = {
  Plan: CalendarRange,
  Practice: Layers,
  Insights: ChartNoAxesColumn,
};

/** A section that isn't built yet: a designed empty state saying honestly when it arrives. */
export function PlaceholderPage({
  title,
  description,
  detail,
}: {
  title: string;
  description: string;
  detail?: string;
}) {
  const Icon = ICONS[title] ?? Sparkles;
  return (
    <>
      <PageHeader title={title} />
      <section className="surface-card flex max-w-2xl flex-col items-start gap-4 rounded-xl p-8 sm:p-10">
        <span
          aria-hidden
          className="bg-accent-soft text-link flex size-12 items-center justify-center rounded-[14px]"
        >
          <Icon className="size-6" />
        </span>
        <div className="grid gap-1.5">
          <p className="type-h3">{description}</p>
          {detail && <p className="text-muted">{detail}</p>}
        </div>
      </section>
    </>
  );
}
