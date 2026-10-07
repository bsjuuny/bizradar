import { formatDday } from "@/lib/format";

/** support_programs.source 허용값 - 마이그레이션의 check 제약과 같은 목록. */
export const SUPPORT_SOURCES = ["kstartup", "bizinfo"] as const;
export type SupportSource = (typeof SUPPORT_SOURCES)[number];

const SOURCE_LABELS: Record<SupportSource, string> = {
  kstartup: "K-Startup",
  bizinfo: "기업마당",
};

export function supportSourceLabel(source: string): string {
  return SOURCE_LABELS[source as SupportSource] ?? source;
}

export function parseSupportSource(value: string | null | undefined): SupportSource | undefined {
  return SUPPORT_SOURCES.find((source) => source === value);
}

/**
 * 마감 칸 표시. 기업마당 공고의 대부분(2026-10-07 기준 65%)은 신청기간이 날짜가 아니라
 * "예산 소진시까지"·"상시 접수" 같은 문장이라 마감일이 비어 있다. 그걸 "일정 미정"으로
 * 뭉개면 실제로는 지금 신청 가능한 공고가 마감 정보 없는 공고처럼 보여서, 원문을 그대로 보여준다.
 */
export function formatSupportDeadline(
  applicationEnd: string | null | undefined,
  periodText: string | null | undefined,
  now: Date = new Date(),
): string {
  if (applicationEnd) return formatDday(applicationEnd, now);
  const text = periodText?.trim();
  return text ? text : formatDday(null, now);
}
