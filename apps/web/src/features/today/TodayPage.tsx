import { PageHeader } from "@/app/PageHeader";

import { SystemStatusCard } from "./SystemStatusCard";

export function TodayPage() {
  return (
    <>
      <PageHeader title="Today" description="Your next study block will appear here." />
      <SystemStatusCard />
    </>
  );
}
