export type NavItem = {
  path: string;
  label: string;
  /** When the page arrives, shown as a placeholder until its phase ships. */
  comingIn: string;
  /** What it will hold, from docs/ROADMAP.md (placeholders only). */
  detail?: string;
};

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Today", comingIn: "" },
  {
    path: "/modules",
    label: "Modules",
    comingIn: "Modules and assessments arrive in Phase 1.",
  },
  { path: "/plan", label: "Plan", comingIn: "" },
  { path: "/practice", label: "Practice", comingIn: "" },
  {
    path: "/insights",
    label: "Insights",
    comingIn: "Insights arrive in Phase 8.",
    detail: "What your own study record shows, each figure labelled measured or estimated.",
  },
  {
    path: "/settings",
    label: "Settings",
    comingIn: "AI provider settings arrive in Phase 2.",
  },
];
