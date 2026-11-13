import { PageHeader } from "@/app/PageHeader";
import { useNow } from "@/lib/useNow";

import { CountdownTiles } from "./CountdownTiles";
import { DayTimeline } from "./DayTimeline";
import { DeadlinesCard } from "./DeadlinesCard";
import { NextUpCard } from "./NextUpCard";
import { SystemStatusCard } from "./SystemStatusCard";

const weekday = new Intl.DateTimeFormat("en-GB", { weekday: "long" });
const dayMonth = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long" });

export function TodayPage() {
  const now = useNow();
  return (
    <>
      <PageHeader
        size="display"
        eyebrow={weekday.format(now)}
        title={dayMonth.format(now)}
        aside={<CountdownTiles now={now} />}
      />
      <div className="grid items-start gap-8 lg:grid-cols-[3fr_2fr]">
        <div className="min-w-0">
          <DayTimeline now={now} />
          <DeadlinesCard />
        </div>
        <div className="grid min-w-0 gap-6">
          <NextUpCard />
          <SystemStatusCard />
        </div>
      </div>
    </>
  );
}
