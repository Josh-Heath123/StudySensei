import {
  BookOpen,
  CalendarDays,
  CalendarRange,
  ChartNoAxesColumn,
  Layers,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { NAV_ITEMS } from "./nav";

const ICONS: Record<string, LucideIcon> = {
  "/": CalendarDays,
  "/modules": BookOpen,
  "/plan": CalendarRange,
  "/practice": Layers,
  "/insights": ChartNoAxesColumn,
  "/settings": Settings,
};

/**
 * The navigation (docs/DESIGN.md "Navigation"): one <nav>, laid out two ways.
 * - From 640 px: a sticky glass bar at the top with the wordmark and the sections.
 * - Below 640 px: the wordmark stays at the top, and the sections become a glass tab bar
 *   fixed to the bottom of the screen, with icons, labels and the safe-area inset.
 * The bar's glass is a separate background layer (not on <header>), because an element with
 * backdrop-filter becomes the containing block of fixed children, which would pin the tab
 * bar to the header instead of the screen.
 */
export function TopNav() {
  return (
    <header className="sticky top-0 z-40 px-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-6 sm:pt-3">
      <div className="relative mx-auto flex max-w-[1392px] items-center gap-x-6 px-4 py-2.5 sm:px-5">
        <div aria-hidden className="glass-nav absolute inset-0 rounded-[20px]" />
        <NavLink
          to="/"
          className="relative flex min-h-9 items-center gap-2 rounded-md text-[17px] font-semibold tracking-[-0.02em]"
        >
          <span aria-hidden className="size-3.5 rounded-full bg-[image:var(--gradient)]" />
          StudySensei
        </NavLink>
        <nav
          aria-label="Main"
          className={cn(
            "max-sm:glass-nav max-sm:fixed max-sm:inset-x-2 max-sm:bottom-[max(0.5rem,env(safe-area-inset-bottom))] max-sm:z-40 max-sm:rounded-[22px] max-sm:p-1.5",
            "sm:relative",
          )}
        >
          <ul className="flex items-center gap-1 max-sm:justify-between">
            {NAV_ITEMS.map(({ path, label }) => {
              const Icon = ICONS[path] ?? CalendarDays;
              return (
                <li key={path} className="shrink-0 max-sm:flex-1">
                  <NavLink
                    to={path}
                    end={path === "/"}
                    className={({ isActive }) =>
                      cn(
                        "inline-flex items-center rounded-[10px] text-sm font-medium transition-colors",
                        "max-sm:min-h-14 max-sm:w-full max-sm:flex-col max-sm:justify-center max-sm:gap-1 max-sm:rounded-[16px] max-sm:text-[11px]",
                        "sm:min-h-9 sm:px-3",
                        isActive
                          ? "text-link sm:bg-accent-soft sm:text-fg max-sm:bg-accent-soft font-semibold"
                          : "text-muted hover:text-fg hover:bg-subtle",
                      )
                    }
                  >
                    <Icon aria-hidden className="size-[22px] sm:hidden" />
                    {label}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
