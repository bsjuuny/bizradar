import { describe, expect, it } from "vitest";
import {
  SUPPORT_FIELDS,
  formatSupportDeadline,
  parseSupportField,
  parseSupportSource,
  parseSupportStatus,
  seoulDateKey,
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

describe("parseSupportStatus", () => {
  it("defaults to open and accepts only known statuses", () => {
    expect(parseSupportStatus(undefined)).toBe("open");
    expect(parseSupportStatus("closing")).toBe("closing");
    expect(parseSupportStatus("all")).toBe("all");
    expect(parseSupportStatus("closed")).toBe("open");
  });
});

describe("SUPPORT_FIELDS", () => {
  // Every category value both sources actually used on 2026-10-07 (DB, after decoding
  // K-Startup's "기술개발(R&amp;D)"). "인력" is shared.
  const KNOWN_CATEGORIES = [
    "시설ㆍ공간ㆍ보육",
    "멘토링ㆍ컨설팅ㆍ교육",
    "사업화",
    "행사ㆍ네트워크",
    "창업교육",
    "글로벌",
    "판로ㆍ해외진출",
    "기술개발(R&D)",
    "정책자금",
    "인력",
    "융자ㆍ보증",
    "경영",
    "기술",
    "금융",
    "수출",
    "내수",
    "창업",
    "기타",
  ];

  it("puts every known category in exactly one group", () => {
    for (const category of KNOWN_CATEGORIES) {
      const groups = SUPPORT_FIELDS.filter((field) =>
        (field.categories as readonly string[]).includes(category),
      );
      expect(groups.map((field) => field.key), category).toHaveLength(1);
    }
  });

  it("maps nothing that isn't a known category", () => {
    const mapped = SUPPORT_FIELDS.flatMap((field) => [...field.categories]);
    expect(mapped.filter((category) => !KNOWN_CATEGORIES.includes(category))).toEqual([]);
  });

  it("parses field keys", () => {
    expect(parseSupportField("rnd")?.label).toBe("기술개발");
    expect(parseSupportField("nope")).toBeUndefined();
  });
});

describe("seoulDateKey", () => {
  it("uses the Seoul calendar day", () => {
    // 2026-10-07 23:30 UTC is already 2026-10-08 in Seoul.
    expect(seoulDateKey(new Date("2026-10-07T23:30:00Z"))).toBe("2026-10-08");
    expect(seoulDateKey(NOW)).toBe("2026-10-07");
  });

  it("shifts by whole days across month ends", () => {
    expect(seoulDateKey(new Date("2026-10-28T03:00:00Z"), 7)).toBe("2026-11-04");
  });
});
