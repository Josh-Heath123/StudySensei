/**
 * An in-memory stand-in for the study-time API (settings, rules, exceptions, the expanded
 * week), as routes for `mockApi`. It keeps what's created and works out the week the way
 * the API does, without timezones (intervals are left empty: the UI shows only totals).
 */
import type { components } from "@/lib/api/schema";

import { json, type Handler } from "./mockApi";

type Rule = components["schemas"]["RuleOut"];
type Exception = components["schemas"]["ExceptionOut"];
type Settings = components["schemas"]["PlanningSettingsOut"];

const minutes = (clock: string) => {
  const [h = "0", m = "0"] = clock.split(":");
  return Number(h) * 60 + Number(m);
};

function weekdayOf(date: string): number {
  return (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7; // Monday is 0
}

function datesFrom(from: string, to: string): string[] {
  const out: string[] = [];
  for (let d = new Date(`${from}T00:00:00Z`); d <= new Date(`${to}T00:00:00Z`);) {
    out.push(d.toISOString().slice(0, 10));
    d = new Date(d.getTime() + 86_400_000);
  }
  return out;
}

export function fakeStudyTime({
  rules = [] as Omit<Rule, "id">[],
  exceptions = [] as Omit<Exception, "id">[],
  settings = { timezone: "Africa/Johannesburg", daily_study_cap_minutes: 180 } as Settings,
} = {}) {
  let next = 0;
  const id = () => `id-${++next}`;
  const state = {
    settings: { ...settings },
    rules: rules.map((rule) => ({ ...rule, id: id() })) as Rule[],
    exceptions: exceptions.map((e) => ({ ...e, id: id() })) as Exception[],
  };
  const overlaps = (weekday: number, start: string, end: string, except?: string) =>
    state.rules.some(
      (r) =>
        r.id !== except &&
        r.weekday === weekday &&
        minutes(start) < minutes(r.end) &&
        minutes(r.start) < minutes(end),
    );
  const sorted = () =>
    state.rules.sort((a, b) => a.weekday - b.weekday || minutes(a.start) - minutes(b.start));

  const routes: Record<string, Handler> = {
    "GET /planning/settings": () => state.settings,
    "PATCH /planning/settings": ({ body }) => {
      Object.assign(state.settings, body);
      return state.settings;
    },
    "GET /availability/rules": () => sorted(),
    "POST /availability/rules": ({ body }) => {
      const rule = body as Omit<Rule, "id">;
      if (overlaps(rule.weekday, rule.start, rule.end)) {
        return json({ detail: "That window overlaps another." }, 409);
      }
      const made = { ...rule, id: id() };
      state.rules.push(made);
      return json(made, 201);
    },
    "PATCH /availability/rules/:id": ({ params, body }) => {
      const rule = state.rules.find((r) => r.id === params.id)!;
      const changed = { ...rule, ...(body as Partial<Rule>) };
      if (minutes(changed.start) >= minutes(changed.end)) {
        return json({ detail: "A window must start before it ends, within one day." }, 422);
      }
      if (overlaps(changed.weekday, changed.start, changed.end, rule.id)) {
        return json({ detail: "That window overlaps another." }, 409);
      }
      Object.assign(rule, changed);
      return rule;
    },
    "DELETE /availability/rules/:id": ({ params }) => {
      state.rules = state.rules.filter((r) => r.id !== params.id);
      return json(null, 204);
    },
    "GET /availability/exceptions": ({ query }) =>
      state.exceptions
        .filter((e) => !query.get("from") || e.date >= query.get("from")!)
        .sort((a, b) => a.date.localeCompare(b.date)),
    "POST /availability/exceptions": ({ body }) => {
      const input = body as Omit<Exception, "id">;
      if (state.exceptions.some((e) => e.date === input.date)) {
        return json({ detail: `${input.date} already has an exception.` }, 409);
      }
      const made = { ...input, windows: input.windows ?? [], note: input.note ?? null, id: id() };
      state.exceptions.push(made);
      return json(made, 201);
    },
    "DELETE /availability/exceptions/:id": ({ params }) => {
      state.exceptions = state.exceptions.filter((e) => e.id !== params.id);
      return json(null, 204);
    },
    "GET /availability": ({ query }) => {
      const cap = state.settings.daily_study_cap_minutes;
      const days = datesFrom(query.get("from")!, query.get("to")!).map((date) => {
        const weekday = weekdayOf(date);
        const exception = state.exceptions.find((e) => e.date === date);
        const windows = exception
          ? exception.windows
          : state.rules.filter((r) => r.weekday === weekday);
        const free = windows.reduce((sum, w) => sum + minutes(w.end) - minutes(w.start), 0);
        return {
          date,
          weekday,
          source: exception ? (exception.unavailable ? "unavailable" : "exception") : "rules",
          intervals: [],
          free_minutes: free,
          available_minutes: Math.min(free, cap),
        };
      });
      const perWeekday = [0, 1, 2, 3, 4, 5, 6].map((weekday) =>
        state.rules
          .filter((r) => r.weekday === weekday)
          .reduce((sum, r) => sum + minutes(r.end) - minutes(r.start), 0),
      );
      return {
        timezone: state.settings.timezone,
        daily_study_cap_minutes: cap,
        days,
        total_free_minutes: days.reduce((sum, d) => sum + d.free_minutes, 0),
        total_available_minutes: days.reduce((sum, d) => sum + d.available_minutes, 0),
        weekly_minutes_from_rules: perWeekday.reduce((sum, m) => sum + Math.min(m, cap), 0),
      };
    },
  };
  return { routes, state };
}
