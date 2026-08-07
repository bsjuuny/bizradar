import { describe, expect, it } from "vitest";
import { formatCurrencyKRW, formatDate, formatDateTime } from "./format";

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
