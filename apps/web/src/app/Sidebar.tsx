import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { NAV_ITEMS } from "./nav";

export function Sidebar() {
  return (
    <aside className="bg-sidebar flex w-56 shrink-0 flex-col border-r px-3 py-5">
      <div className="mb-6 flex items-center gap-2 px-2">
        <img src="/favicon.svg" alt="" className="size-6" />
        <span className="font-semibold tracking-tight">StudySensei</span>
      </div>
      <nav aria-label="Main">
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
            <li key={path}>
              <NavLink
                to={path}
                end={path === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
