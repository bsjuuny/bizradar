import { formatDday } from "@/lib/format";
import { enumValue } from "@/lib/search-params";

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
  return enumValue(value ?? "", SUPPORT_SOURCES);
}

/**
 * 모집 상태 필터. 기본값은 "open" - 마감된 공고가 전체의 대부분이라(2026-10-07: 2,493건 중
 * K-Startup 910건이 마감) 기본으로 보여주면 신청할 수 있는 공고가 묻힌다.
 * - open: 모집 중(recruiting)이고 마감일이 없거나 오늘 이후 - DB 함수 support_program_is_open
 *   (supabase/migrations/20261007130000_support_programs_listing.sql)이 유일한 정의다.
 *   마감일 조건까지 거는 이유는 K-Startup의 모집 여부 플래그가 마감일보다 늦게 바뀌는
 *   경우가 있어서다(16건 실측).
 * - closing: open 중 마감일이 오늘부터 CLOSING_SOON_DAYS일 안. 날짜 없는 공고는 빠진다.
 * - all: 마감 포함 전부.
 */
export const SUPPORT_STATUSES = ["open", "closing", "all"] as const;
export type SupportStatus = (typeof SUPPORT_STATUSES)[number];
export const DEFAULT_SUPPORT_STATUS: SupportStatus = "open";
/** Label only - the window itself is `interval '7 days'` in list_support_programs (SQL). */
export const CLOSING_SOON_DAYS = 7;

export const SUPPORT_STATUS_LABELS: Record<SupportStatus, string> = {
  open: "모집 중",
  closing: `${CLOSING_SOON_DAYS}일 안에 마감`,
  all: "마감 포함 전체",
};

export function parseSupportStatus(value: string | null | undefined): SupportStatus {
  return enumValue(value ?? "", SUPPORT_STATUSES) ?? DEFAULT_SUPPORT_STATUS;
}

/**
 * 지원분야 통합 필터. K-Startup(supt_biz_clsfc)과 기업마당(지원분야 대분류)은 분류 체계가
 * 달라서, 공통 묶음 하나에 두 출처의 원래 값을 대응시킨다. categories는 DB에 저장된 값과
 * 글자 그대로 같아야 한다(가운뎃점은 'ㆍ' U+318D) - 2026-10-07 두 출처에 실제로 있는 값 18개
 * ("인력"은 양쪽 공통) 전부가 정확히 한 묶음에 들어가는지 support-display.test.ts가 확인한다.
 * 출처에 새 분류가 생기면 어느 묶음에도 안 들어가 분야 필터에서만 빠진다(목록에는 계속 보임).
 */
export const SUPPORT_FIELDS = [
  { key: "funding", label: "자금·융자", categories: ["금융", "정책자금", "융자ㆍ보증"] },
  { key: "rnd", label: "기술개발", categories: ["기술", "기술개발(R&D)"] },
  { key: "startup", label: "창업·사업화", categories: ["창업", "사업화"] },
  { key: "space", label: "공간·보육", categories: ["시설ㆍ공간ㆍ보육"] },
  {
    key: "market",
    label: "판로·수출",
    categories: ["수출", "내수", "판로ㆍ해외진출", "글로벌"],
  },
  {
    key: "consulting",
    label: "경영·컨설팅·교육",
    categories: ["경영", "멘토링ㆍ컨설팅ㆍ교육", "창업교육"],
  },
  { key: "hr", label: "인력", categories: ["인력"] },
  { key: "event", label: "행사·네트워크", categories: ["행사ㆍ네트워크"] },
  { key: "etc", label: "기타", categories: ["기타"] },
] as const;
export type SupportField = (typeof SUPPORT_FIELDS)[number];
export type SupportFieldKey = SupportField["key"];

export function parseSupportField(value: string | null | undefined): SupportField | undefined {
  return SUPPORT_FIELDS.find((field) => field.key === value);
}

/**
 * 마감 칸 표시. 기업마당 공고의 대부분(2026-10-07 기준 65%)은 신청기간이 날짜가 아니라
 * "예산 소진시까지"·"상시 접수" 같은 문장이라 마감일이 비어 있다. 그걸 "일정 미정"으로
 * 뭉개면 실제로는 지금 신청 가능한 공고가 마감 정보 없는 공고처럼 보여서, 원문을 그대로 보여준다.
 */
export function formatSupportDeadline(
  applicationEnd: string | null | undefined,
  periodText: string | null | undefined,
  isOpen: boolean,
  now: Date = new Date(),
): string {
  // is_open (support_program_is_open) decides, the same as the list filter and the
  // detail page's 모집상태: a posting that isn't open must not read as open - "예산
  // 소진시까지" or a future D-N would suggest it still takes applications.
  if (!isOpen) return "마감";
  if (applicationEnd) return formatDday(applicationEnd, now);
  const text = periodText?.trim();
  return text ? text : formatDday(null, now);
}
