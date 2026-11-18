import { Outlet } from "react-router";

import { TopNav } from "./TopNav";

/**
 * Every page sits in one container (docs/DESIGN.md "Layout": 1120 px, centred), so a page's
 * header and its content share edges: header actions line up with the content's right edge.
 * On phones the navigation is a bottom tab bar, so the page keeps room for it.
 */
export function AppLayout() {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-[1120px] px-4 pt-6 pb-[calc(6.5rem+env(safe-area-inset-bottom))] sm:px-8 sm:pt-12 sm:pb-16 lg:px-10">
        <Outlet />
      </main>
    </div>
  );
}
