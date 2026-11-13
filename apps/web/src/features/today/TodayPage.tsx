import { PageHeader } from "@/app/PageHeader";

import { DeadlinesCard } from "./DeadlinesCard";
import { SystemStatusCard } from "./SystemStatusCard";

const todayFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

export function TodayPage() {
  return (
    <>
      <PageHeader title="Today" description={todayFormat.format(new Date())} />
      <DeadlinesCard />
      <SystemStatusCard />
    </>
  );
}
