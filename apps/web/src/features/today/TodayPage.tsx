import { PageHeader } from "@/app/PageHeader";
import { useNow } from "@/lib/useNow";

import { CountdownTiles } from "./CountdownTiles";
import { DayTimeline } from "./DayTimeline";
import { DeadlinesCard } from "./DeadlinesCard";
import { NextUpCard } from "./NextUpCard";
import { SystemStatusCard } from "./SystemStatusCard";

const weekday = new Intl.DateTimeFormat("en-GB", { weekday: "long" });
const dayMonth = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long" });

/**
 * docs/DESIGN.md "Screens: Today": the editorial date, the "Next up" hero, then the
 * calm, solid day and deadlines. Next up comes first in the DOM so it leads on small
 * screens; from 1024 px it sits in the right column above the (quiet) system status.
 */
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
      <div className="grid items-start gap-6 lg:grid-cols-[3fr_2fr] lg:grid-rows-[auto_1fr] lg:gap-8">
        <div className="min-w-0 lg:col-start-2 lg:row-start-1">
          <NextUpCard />
        </div>
        <div className="grid min-w-0 gap-6 lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:gap-8">
          <DayTimeline />
          <DeadlinesCard />
        </div>
        <div className="min-w-0 lg:col-start-2 lg:row-start-2">
          <SystemStatusCard />
        </div>
      </div>
    </>
  );
}
