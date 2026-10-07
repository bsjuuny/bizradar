import { describe, expect, it } from "vitest";
import {
  formatCurrencyKRW,
  formatDate,
  formatDateTime,
  formatDday,
  seoulDateKey,
} from "./format";

describe("seoulDateKey", () => {
  it("uses the Seoul calendar day", () => {
    // 2026-10-07 23:30 UTC is already 2026-10-08 in Seoul.
    expect(seoulDateKey(new Date("2026-10-07T23:30:00Z"))).toBe("2026-10-08");
    expect(seoulDateKey(new Date("2026-10-07T03:00:00Z"))).toBe("2026-10-07");
  });
});

describe("formatCurrencyKRW", () => {
  it("formats a number with thousands separators and 원 suffix", () => {
    expect(formatCurrencyKRW(150000000)).toBe("150,000,000원");
  });

  it("returns an em dash for null/undefined", () => {
    expect(formatCurrencyKRW(null)).toBe("—");
    expect(formatCurrencyKRW(undefined)).toBe("—");
  });

  it("formats zero as an actual zero, not a dash", () => {
    expect(formatCurrencyKRW(0)).toBe("0원");
  });
});

describe("formatDate", () => {
  it("truncates an ISO timestamp to the date part", () => {
    expect(formatDate("2026-08-04T08:25:58+00:00")).toBe("2026-08-04");
  });

  it("returns an em dash for null/empty", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("")).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("formats a valid ISO timestamp", () => {
    const result = formatDateTime("2026-08-04T08:25:58+00:00");
    expect(result).not.toBe("—");
    expect(result).toContain("2026");
  });

  it("returns an em dash for null or invalid input", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });
});

describe("formatDday", () => {
  const now = new Date("2026-08-07T03:00:00Z");

  it("calculates a Seoul-calendar D-day", () => {
    expect(formatDday("2026-08-17T14:59:59Z", now)).toBe("D-10");
    expect(formatDday("2026-08-07T14:59:59Z", now)).toBe("D-Day");
  });

  it("handles closed, missing, and invalid deadlines", () => {
    expect(formatDday("2026-08-06T14:59:59Z", now)).toBe("마감");
    expect(formatDday(null, now)).toBe("일정 미정");
    expect(formatDday("invalid", now)).toBe("일정 미정");
  });
});
