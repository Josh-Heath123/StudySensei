import {
  addDays,
  fromInput,
  hoursText,
  localToday,
  nextWindow,
  shortDate,
  timezoneOptions,
  toInput,
  windowLength,
} from "./studyTime";

test("midnight as an end is 24:00 for the API and 00:00 in a time input", () => {
  expect(toInput("24:00")).toBe("00:00");
  expect(toInput("18:30")).toBe("18:30");
  expect(fromInput("00:00", true)).toBe("24:00");
  expect(fromInput("00:00", false)).toBe("00:00");
});

test("a window's length", () => {
  expect(windowLength({ start: "18:00", end: "20:30" })).toBe(150);
  expect(windowLength({ start: "22:00", end: "24:00" })).toBe(120);
  expect(windowLength({ start: "20:00", end: "18:00" })).toBe(0);
});

test("a new window goes after the last one, never past midnight", () => {
  expect(nextWindow([])).toEqual({ start: "18:00", end: "19:00" });
  expect(nextWindow([{ start: "09:00", end: "12:00" }])).toEqual({
    start: "12:00",
    end: "13:00",
  });
  expect(nextWindow([{ start: "22:00", end: "23:30" }])).toEqual({
    start: "23:30",
    end: "24:00",
  });
  expect(nextWindow([{ start: "22:00", end: "24:00" }])).toBeNull();
});

test("hours for the summary, to the nearest half hour", () => {
  expect(hoursText(45)).toBe("45 min");
  expect(hoursText(720)).toBe("12 h");
  expect(hoursText(750)).toBe("12.5 h");
  expect(hoursText(760)).toBe("12.5 h");
});

test("today in the user's timezone, not the device's", () => {
  const lateUtc = new Date("2026-11-19T23:30:00Z");
  expect(localToday("Africa/Johannesburg", lateUtc)).toBe("2026-11-20");
  expect(localToday("Europe/London", lateUtc)).toBe("2026-11-19");
});

test("dates move by whole days across months and years", () => {
  expect(addDays("2026-11-29", 6)).toBe("2026-12-05");
  expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  expect(shortDate("2026-11-27")).toBe("Fri 27 Nov");
});

test("the current timezone is always offered", () => {
  expect(timezoneOptions("Africa/Johannesburg")).toContain("Africa/Johannesburg");
  expect(timezoneOptions("Not/AZone")[0]).toBe("Not/AZone");
});
