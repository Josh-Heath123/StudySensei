import { Outlet } from "react-router";

import { TopNav } from "./TopNav";

export function AppLayout() {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-[1392px] px-4 pt-8 pb-16 sm:px-8 sm:pt-12 lg:px-10">
        <Outlet />
      </main>
    </div>
  );
}
