import {
  addDays,
  dayLabel,
  fromZoned,
  hourRange,
  mondayOf,
  snap5,
  startsWithin,
  toSpans,
  weekDates,
  zoned,
} from "./week";

const SAST = "Africa/Johannesburg";

test("local dates and minutes are in the user's timezone, not the browser's", () => {
  // 16:00 UTC is 18:00 in Johannesburg; 23:30 UTC is 01:30 the next day there.
  expect(zoned("2026-11-24T16:00:00Z", SAST)).toEqual({ date: "2026-11-24", minutes: 18 * 60 });
  expect(zoned("2026-11-24T23:30:00Z", SAST)).toEqual({ date: "2026-11-25", minutes: 90 });
  expect(fromZoned("2026-11-24", 18 * 60, SAST).toISOString()).toBe("2026-11-24T16:00:00.000Z");
});

test("fromZoned survives a DST change (Europe/London, 29 March 2026)", () => {
  const london = "Europe/London";
  expect(fromZoned("2026-03-28", 18 * 60, london).toISOString()).toBe("2026-03-28T18:00:00.000Z");
  expect(fromZoned("2026-03-30", 18 * 60, london).toISOString()).toBe("2026-03-30T17:00:00.000Z");
});

test("weeks start on Monday", () => {
  expect(mondayOf("2026-11-26")).toBe("2026-11-23"); // Thursday
  expect(mondayOf("2026-11-29")).toBe("2026-11-23"); // Sunday
  expect(weekDates("2026-11-23")).toHaveLength(7);
  expect(weekDates("2026-11-23")[6]).toBe("2026-11-29");
  expect(addDays("2026-11-30", 2)).toBe("2026-12-02");
  expect(dayLabel("2026-11-24")).toBe("Tue 24 Nov");
});

test("the hour range covers the week's windows and blocks, not the whole day", () => {
  const spans = [
    ...toSpans("2026-11-24T16:00:00Z", "2026-11-24T19:00:00Z", SAST), // 18:00-21:00
    ...toSpans("2026-11-28T07:15:00Z", "2026-11-28T08:05:00Z", SAST), // 09:15-10:05
  ];
  expect(hourRange(spans)).toEqual({ first: 9, last: 21 });
  expect(hourRange([])).toBeNull();
});

test("snapping and the starts a free window allows", () => {
  expect(snap5(1082)).toBe(1080);
  expect(snap5(1083)).toBe(1085);
  const evening = [{ date: "2026-11-24", start: 18 * 60, end: 19 * 60 }];
  expect(startsWithin(evening, 50)).toEqual([1080, 1085, 1090]);
});
