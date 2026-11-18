import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { NAV_ITEMS } from "./nav";

/**
 * The top bar (docs/DESIGN.md "Top navigation"): a sticky glass bar with the wordmark and
 * the sections. On narrow screens the sections become a row that scrolls sideways, so every
 * section stays one tap away without a menu.
 */
export function TopNav() {
  return (
    <header className="sticky top-0 z-40 px-3 pt-3 sm:px-6">
      <div className="glass-strong mx-auto flex max-w-[1392px] flex-wrap items-center gap-x-6 gap-y-2 rounded-[20px] px-4 py-2.5 sm:flex-nowrap sm:px-5">
        <NavLink
          to="/"
          className="flex items-center gap-2 rounded-md text-[17px] font-semibold tracking-[-0.02em]"
        >
          <span aria-hidden className="size-3.5 rounded-full bg-[image:var(--gradient)]" />
          StudySensei
        </NavLink>
        <nav
          aria-label="Main"
          className="-mx-1 w-full min-w-0 overflow-x-auto [mask-image:linear-gradient(to_right,black_85%,transparent)] sm:mx-0 sm:w-auto sm:[mask-image:none]"
        >
          <ul className="flex items-center gap-1">
            {NAV_ITEMS.map(({ path, label }) => (
              <li key={path} className="shrink-0">
                <NavLink
                  to={path}
                  end={path === "/"}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex min-h-9 items-center rounded-[10px] px-3 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent-soft text-fg font-semibold"
                        : "text-muted hover:text-fg hover:bg-subtle",
                    )
                  }
                >
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
