import {
  BookOpen,
  CalendarDays,
  ChartLine,
  type LucideIcon,
  Settings,
  Sun,
  Target,
} from "lucide-react";

export type NavItem = {
  path: string;
  label: string;
  icon: LucideIcon;
  /** What the page will hold, shown as a placeholder until its phase ships. */
  comingIn: string;
};

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Today", icon: Sun, comingIn: "" },
  {
    path: "/modules",
    label: "Modules",
    icon: BookOpen,
    comingIn: "Modules and assessments arrive in Phase 1.",
  },
  {
    path: "/plan",
    label: "Plan",
    icon: CalendarDays,
    comingIn: "The study planner arrives in Phase 4.",
  },
  {
    path: "/practice",
    label: "Practice",
    icon: Target,
    comingIn: "Practice and reviews arrive in Phase 5.",
  },
  {
    path: "/insights",
    label: "Insights",
    icon: ChartLine,
    comingIn: "Insights arrive in Phase 8.",
  },
  {
    path: "/settings",
    label: "Settings",
    icon: Settings,
    comingIn: "AI provider settings arrive in Phase 2.",
  },
];
