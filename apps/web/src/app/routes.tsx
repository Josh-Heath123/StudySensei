import type { RouteObject } from "react-router";

import { ModuleDetailPage } from "@/features/modules/ModuleDetailPage";
import { ModulesPage } from "@/features/modules/ModulesPage";
import { SessionPage } from "@/features/session/SessionPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { TodayPage } from "@/features/today/TodayPage";

import { AppLayout } from "./AppLayout";
import { NAV_ITEMS } from "./nav";
import { PlaceholderPage } from "./PlaceholderPage";

const BUILT = new Set(["/", "/modules", "/settings"]);

// Feature pages replace these placeholders as each phase lands.
const placeholders: RouteObject[] = NAV_ITEMS.filter((item) => !BUILT.has(item.path)).map(
  (item) => ({
    path: item.path,
    element: (
      <PlaceholderPage title={item.label} description={item.comingIn} detail={item.detail} />
    ),
  }),
);

export const routes: RouteObject[] = [
  // Focus mode: the session screen has its own header instead of the top nav.
  { path: "/session", element: <SessionPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <TodayPage /> },
      { path: "/modules", element: <ModulesPage /> },
      { path: "/modules/:moduleId", element: <ModuleDetailPage /> },
      { path: "/settings", element: <SettingsPage /> },
      ...placeholders,
    ],
  },
];
