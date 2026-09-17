import { isOpenToAll, type OpportunitySummary } from "@/lib/opportunities";

/**
 * "업종·지역 제한 없음" 배지 - 실적이나 업종 요건 때문에 지원 자체가 막히는지를
 * 목록에서 바로 알아보게 한다. 매칭 점수가 "우리에게 맞는가"라면 이건 "우리가
 * 지원할 수 있는가"라서, 신규·소규모 업체에는 점수보다 먼저 걸리는 관문이다.
 *
 * 제한이 있는 경우는 배지를 띄우지 않는다 - 대부분의 공고가 거기 해당해서
 * (최근 7일 LIKELY_IT 328건 중 제한 없는 건 106건) 전부 배지를 달면 목록이
 * 배지로 뒤덮여 오히려 안 읽힌다. 눈에 띄어야 할 쪽만 표시한다.
 */
export function OpenToAllBadge({
  opportunity,
}: {
  opportunity: Pick<OpportunitySummary, "industry_limited" | "region_restriction">;
}) {
  if (!isOpenToAll(opportunity)) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return (
    <span
      className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium whitespace-nowrap text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
      title="업종제한·지역제한이 모두 없는 공고입니다. 공고에 명시되지 않은 경우는 제한 없음으로 보지 않습니다."
    >
      누구나 지원
    </span>
  );
}
