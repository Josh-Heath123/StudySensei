import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { NAV_ITEMS } from "./nav";

/** The top bar (docs/DESIGN.md "Top navigation"): wordmark, then the sections. Wraps on small screens. */
export function TopNav() {
  return (
    <header className="border-ink border-b-2">
      <div className="flex min-h-16 flex-wrap items-center gap-x-8 gap-y-2 px-5 py-3 sm:px-10">
        <NavLink to="/" className="font-display text-xl font-bold tracking-tight">
          StudySensei
        </NavLink>
        <nav aria-label="Main">
          <ul className="flex flex-wrap items-center gap-x-6 gap-y-1">
            {NAV_ITEMS.map(({ path, label }) => (
              <li key={path}>
                <NavLink
                  to={path}
                  end={path === "/"}
                  className={({ isActive }) =>
                    cn(
                      "inline-block border-b-[3px] py-1 text-sm transition-colors",
                      isActive
                        ? "text-ink border-[var(--module)] font-semibold"
                        : "text-muted hover:text-ink border-transparent",
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
