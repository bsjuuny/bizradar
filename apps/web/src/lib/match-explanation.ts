import type { MatchScoreBreakdown } from "./opportunities";
import { formatDday } from "./format";

// worker/matching/engine.py의 실제 채점 방식을 그대로 반영한다: technology/schedule을
// 제외한 5개 카테고리는 엄격히 0점 아니면 만점(이분법)이고, technology는 매칭 비율에
// 비례, schedule은 마감까지 남은 일수(7일 기준)에 비례한다. 여기서는 그 사실을 다시
// 계산하지 않고, 이미 계산된 점수/만점 비율만으로 진짜인 설명을 만든다 - 원문 데이터
// (회사 프로필, AI 분석 결과)를 다시 들여다보지 않아도 엔진의 실제 동작과 어긋나지 않는다.

export type MatchVerdict = "full" | "partial" | "none";

export type MatchExplanationItem = {
  key: keyof MatchScoreBreakdown;
  label: string;
  score: number;
  max: number;
  verdict: MatchVerdict;
  message: string;
};

const MAX_SCORES: Record<
  Exclude<keyof MatchScoreBreakdown, "total_score">,
  number
> = {
  technology_score: 30,
  business_type_score: 20,
  budget_score: 15,
  experience_score: 15,
  qualification_score: 10,
  region_score: 5,
  schedule_score: 5,
};

function verdictFor(score: number, max: number): MatchVerdict {
  if (score <= 0) return "none";
  if (score >= max) return "full";
  return "partial";
}

function technologyMessage(verdict: MatchVerdict): string {
  if (verdict === "full") return "요구 기술을 모두 보유했거나, 이 공고는 특정 기술을 요구하지 않습니다.";
  if (verdict === "none") return "요구 기술을 보유하고 있지 않습니다.";
  return "요구 기술 중 일부만 보유하고 있습니다.";
}

function businessTypeMessage(verdict: MatchVerdict): string {
  return verdict === "full"
    ? "사업 형태가 이 공고 유형과 맞거나, 별도 사업 형태 요건이 없습니다."
    : "사업 형태가 이 공고 유형과 다르거나, 회사 프로필에 사업 형태가 입력되어 있지 않습니다.";
}

function budgetMessage(verdict: MatchVerdict, budgetAmount: number | null | undefined): string {
  // 엔진은 opp.budget_amount가 없으면 회사 설정과 무관하게 무조건 만점을 준다 - "예산
  // 정보가 아예 없어서"와 "회사가 예산 조건을 안 걸어서"는 다른 이유라 구분해야 한다.
  if (verdict === "full" && (budgetAmount === null || budgetAmount === undefined)) {
    return "이 공고에는 예산 정보가 없어 감점하지 않았습니다.";
  }
  return verdict === "full"
    ? "회사가 설정한 예산 범위 안이거나, 예산 조건을 별도로 설정하지 않았습니다."
    : "회사가 설정에서 지정한 예산 범위를 벗어납니다.";
}

function experienceMessage(verdict: MatchVerdict): string {
  return verdict === "full"
    ? "요구 경력 연차를 충족했거나, 별도 경력 요건이 없습니다."
    : "이 공고가 요구하는 경력 연차에 못 미칩니다.";
}

function qualificationMessage(verdict: MatchVerdict): string {
  return verdict === "full"
    ? "요구 자격/인증을 모두 보유했거나, 별도 자격 요건이 없습니다."
    : "요구 자격/인증 중 회사 프로필에 없는 항목이 있습니다.";
}

function regionMessage(verdict: MatchVerdict): string {
  return verdict === "full"
    ? "지역 제한이 없거나, 회사 소재지가 지역 제한 조건과 일치합니다."
    : "공고의 지역 제한과 회사 소재지가 다르거나, 회사 소재지가 입력되어 있지 않습니다.";
}

function scheduleMessage(verdict: MatchVerdict, bidCloseAt: string | null | undefined): string {
  // bid_close_at이 없으면 엔진은 감점하지 않고 만점을 준다 - "7일 이상 여유"와는 다른 의미이므로 구분한다.
  if (!bidCloseAt) return "마감일 정보가 없어 일정 항목은 감점하지 않았습니다.";
  if (verdict === "full") return "마감까지 여유가 있습니다 (7일 이상).";
  // formatDday는 서울 달력일 기준이라, 엔진의 초 단위 채점과 달리 "오늘 이미 지남"과
  // "오늘이 마감"을 구분하지 못한다 - 과대확신하지 않도록 두 경우를 하나의 문구로 묶는다.
  if (verdict === "none") return "마감이 임박했거나 이미 지났습니다.";
  return `마감이 임박했습니다 (${formatDday(bidCloseAt)}).`;
}

/**
 * 이미 계산된 match_scores 7개 항목을 사람이 읽을 수 있는 한 줄 설명으로 바꾼다.
 * 숫자만으로는 "왜 이 점수인지" 알기 어렵다는 문제를 해결하기 위한 것으로,
 * 매칭 알고리즘을 다시 판정하지 않고 이미 나온 점수를 설명만 한다.
 */
export function explainMatchBreakdown(
  breakdown: MatchScoreBreakdown,
  options: { bidCloseAt?: string | null; budgetAmount?: number | null } = {},
): MatchExplanationItem[] {
  const entries: [keyof typeof MAX_SCORES, string, (v: MatchVerdict) => string][] = [
    ["technology_score", "기술", technologyMessage],
    ["business_type_score", "사업 형태", businessTypeMessage],
    ["budget_score", "예산", (v) => budgetMessage(v, options.budgetAmount)],
    ["experience_score", "경력", experienceMessage],
    ["qualification_score", "자격/인증", qualificationMessage],
    ["region_score", "지역", regionMessage],
    ["schedule_score", "일정", (v) => scheduleMessage(v, options.bidCloseAt)],
  ];

  return entries.map(([key, label, messageFn]) => {
    const score = breakdown[key];
    const max = MAX_SCORES[key];
    const verdict = verdictFor(score, max);
    return { key, label, score, max, verdict, message: messageFn(verdict) };
  });
}
