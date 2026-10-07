import { describe, expect, it } from "vitest";
import {
  formatSupportDeadline,
  parseSupportSource,
  supportSourceLabel,
} from "./support-display";

const NOW = new Date("2026-10-07T03:00:00Z"); // 2026-10-07 12:00 KST

describe("supportSourceLabel", () => {
  it("names both sources", () => {
    expect(supportSourceLabel("kstartup")).toBe("K-Startup");
    expect(supportSourceLabel("bizinfo")).toBe("기업마당");
  });

  it("falls back to the raw value for an unknown source", () => {
    expect(supportSourceLabel("smes")).toBe("smes");
  });
});

describe("parseSupportSource", () => {
  it("accepts only known sources", () => {
    expect(parseSupportSource("bizinfo")).toBe("bizinfo");
    expect(parseSupportSource("kstartup")).toBe("kstartup");
    expect(parseSupportSource("all")).toBeUndefined();
    expect(parseSupportSource(undefined)).toBeUndefined();
  });
});

describe("formatSupportDeadline", () => {
  it("uses the D-day when there is a deadline date", () => {
    expect(formatSupportDeadline("2026-10-16T00:00:00+00:00", "2026-10-02 ~ 2026-10-16", NOW)).toBe(
      "D-9",
    );
  });

  it("shows the source's own wording when the period isn't a date", () => {
    expect(formatSupportDeadline(null, "예산 소진시까지", NOW)).toBe("예산 소진시까지");
  });

  it("falls back to 일정 미정 when there is neither", () => {
    expect(formatSupportDeadline(null, null, NOW)).toBe("일정 미정");
    expect(formatSupportDeadline(null, "  ", NOW)).toBe("일정 미정");
  });
});
