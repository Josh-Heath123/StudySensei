export type NavItem = {
  path: string;
  label: string;
  /** What the page will hold, shown as a placeholder until its phase ships. */
  comingIn: string;
};

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Today", comingIn: "" },
  {
    path: "/modules",
    label: "Modules",
    comingIn: "Modules and assessments arrive in Phase 1.",
  },
  {
    path: "/plan",
    label: "Plan",
    comingIn: "The study planner arrives in Phase 4.",
  },
  {
    path: "/practice",
    label: "Practice",
    comingIn: "Practice and reviews arrive in Phase 5.",
  },
  {
    path: "/insights",
    label: "Insights",
    comingIn: "Insights arrive in Phase 8.",
  },
  {
    path: "/settings",
    label: "Settings",
    comingIn: "AI provider settings arrive in Phase 2.",
  },
];
