import type { RouteObject } from "react-router";

import { TodayPage } from "@/features/today/TodayPage";

import { AppLayout } from "./AppLayout";
import { NAV_ITEMS } from "./nav";
import { PlaceholderPage } from "./PlaceholderPage";

// Feature pages replace these placeholders as each phase lands.
const placeholders: RouteObject[] = NAV_ITEMS.filter((item) => item.path !== "/").map((item) => ({
  path: item.path,
  element: <PlaceholderPage title={item.label} description={item.comingIn} />,
}));

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [{ index: true, element: <TodayPage /> }, ...placeholders],
  },
];
