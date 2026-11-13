import { Outlet } from "react-router";

import { TopNav } from "./TopNav";

export function AppLayout() {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-[1440px] px-5 py-8 sm:px-10 sm:py-10">
        <Outlet />
      </main>
    </div>
  );
}
