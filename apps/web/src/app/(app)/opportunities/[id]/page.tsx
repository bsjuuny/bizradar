import Link from "next/link";
import { notFound } from "next/navigation";
import { getOpportunity, getNoticeRevisionChanges, type NoticeChange } from "@/lib/opportunities";
import { getOrganizationAwardHistory } from "@/lib/awards";
import { formatCurrencyKRW, formatDate, formatDateTime } from "@/lib/format";
import { explainMatchBreakdown } from "@/lib/match-explanation";
import { CategoryBadge } from "../category-badge";
import { MatchScoreBadge } from "../match-score-badge";

const PROJECT_TYPE_LABELS: Record<string, string> = {
  SYSTEM_BUILD: "시스템 구축",
  MAINTENANCE: "유지보수",
  CONSULTING: "컨설팅",
  DATA_ANALYTICS: "데이터 분석",
  AI_ML: "AI/ML",
  INFRASTRUCTURE: "인프라",
  OTHER: "기타",
};

function formatChangeValue(field: NoticeChange["field"], value: string | number | null): string {
  if (value === null) return "미정";
  if (field === "bid_close_at" || field === "open_at") return formatDateTime(String(value));
  if (field === "budget_amount") return formatCurrencyKRW(Number(value));
  return String(value);
}

export default async function OpportunityDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ from?: string }>;
}) {
  const { id } = await params;
  const { from } = await searchParams;
  const opportunity = await getOpportunity(id);
  if (!opportunity) notFound();

  const analysis = opportunity.analysis?.status === "SUCCESS" ? opportunity.analysis : null;
  const organizationWinners = opportunity.organization
    ? await getOrganizationAwardHistory(opportunity.organization, {
        excludeBidNtceNo: opportunity.bid_ntce_no,
      })
    : [];
  const revisionChanges = await getNoticeRevisionChanges(opportunity.bid_ntce_no, opportunity.bid_ntce_ord);
  // `from` is the list page's own search/filter/page query string, passed through by
  // its row links (see opportunities/page.tsx) so this restores that exact view instead
  // of resetting to the default list.
  const backHref = from ? `/opportunities?${from}` : "/opportunities";

  return (
    <div className="flex flex-col gap-6">
      <Link href={backHref} className="text-sm text-muted-foreground hover:underline">
        ← Project Radar 목록으로
      </Link>

      <header className="flex flex-col gap-3 border-b border-border pb-6">
        <div className="flex flex-wrap items-center gap-2">
          <CategoryBadge category={opportunity.category} />
          <MatchScoreBadge score={opportunity.matchScore} />
        </div>
        <h1 className="max-w-4xl text-2xl font-semibold leading-snug text-balance">{opportunity.title}</h1>
        <p className="text-sm text-muted-foreground">{opportunity.organization ?? "공고기관 미확인"}</p>
      </header>

      {revisionChanges.length > 0 && (
        <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900 dark:bg-amber-950/20">
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
            변경공고 - 이전 공고 대비 아래 항목이 바뀌었습니다.
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-sm text-amber-900/90 dark:text-amber-200/90">
            {revisionChanges.map((change) => (
              <li key={change.field}>
                <span className="font-medium">{change.label}</span>: {formatChangeValue(change.field, change.previousValue)}
                {" → "}
                {formatChangeValue(change.field, change.currentValue)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {opportunity.matchBreakdown && (
        <section className="rounded-lg border border-border p-5">
          <h2 className="text-sm font-semibold">Company Match</h2>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            {explainMatchBreakdown(opportunity.matchBreakdown, {
              bidCloseAt: opportunity.bid_close_at,
              budgetAmount: opportunity.budget_amount,
            }).map(
              ({ key, label, score, max, verdict, message }) => (
                <div key={key} className="flex items-start justify-between gap-3 rounded-md bg-muted/30 p-3">
                  <div className="min-w-0">
                    <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
                    <dd className="mt-0.5 text-xs text-muted-foreground">{message}</dd>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums ${
                      verdict === "full"
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                        : verdict === "partial"
                          ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                          : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {Math.round(score)} / {max}
                  </span>
                </div>
              ),
            )}
          </dl>
        </section>
      )}

      <dl className="grid grid-cols-1 gap-x-8 gap-y-3 rounded-lg border border-border p-5 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">공고기관</dt>
          <dd>{opportunity.organization ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">수요기관</dt>
          <dd>{opportunity.demand_organization ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">배정예산</dt>
          <dd className="tabular-nums">{formatCurrencyKRW(opportunity.budget_amount)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">추정가격</dt>
          <dd className="tabular-nums">{formatCurrencyKRW(opportunity.estimated_price)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">지역제한</dt>
          <dd>{opportunity.region_restriction ?? "제한 없음"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">게시일</dt>
          <dd>{formatDateTime(opportunity.posted_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">입찰마감</dt>
          <dd>{formatDateTime(opportunity.bid_close_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">개찰일시</dt>
          <dd>{formatDateTime(opportunity.open_at)}</dd>
        </div>
      </dl>

      {opportunity.award && (
        <section className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-5 dark:border-emerald-900 dark:bg-emerald-950/20">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">낙찰 결과</h2>
            <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100">
              낙찰
            </span>
          </div>
          <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">낙찰업체</dt>
              <dd className="font-medium">{opportunity.award.winner_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">낙찰금액</dt>
              <dd className="tabular-nums">{formatCurrencyKRW(opportunity.award.award_amount)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">낙찰률</dt>
              <dd className="tabular-nums">
                {opportunity.award.award_rate === null
                  ? "—"
                  : `${opportunity.award.award_rate.toLocaleString("ko-KR", { maximumFractionDigits: 4 })}%`}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">예정가격</dt>
              <dd className="tabular-nums">{formatCurrencyKRW(opportunity.award.planned_price)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">참가업체 수</dt>
              <dd className="tabular-nums">
                {opportunity.award.participant_count === null
                  ? "—"
                  : `${opportunity.award.participant_count.toLocaleString("ko-KR")}개사`}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">개찰일시</dt>
              <dd>{formatDateTime(opportunity.award.opened_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">낙찰일</dt>
              <dd>{formatDate(opportunity.award.awarded_at)}</dd>
            </div>
          </dl>
        </section>
      )}

      {organizationWinners.length > 0 && (
        <section className="rounded-lg border border-border p-5">
          <h2 className="text-sm font-semibold">이 발주처 최근 낙찰 이력</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {opportunity.organization}의 최근 공고 중 낙찰 결과가 확인된 건에서 자주 낙찰된 업체입니다.
          </p>
          <ul className="mt-4 flex flex-col gap-2">
            {organizationWinners.map((winner, index) => (
              <li
                key={winner.winnerName}
                className="flex items-center justify-between gap-3 rounded-md bg-muted/30 px-3 py-2 text-sm"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground tabular-nums">{index + 1}</span>
                  <span className="truncate font-medium">{winner.winnerName}</span>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                  <span className="tabular-nums">{winner.winCount}회 낙찰</span>
                  <span className="tabular-nums">{formatCurrencyKRW(winner.totalAwardAmount)}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {analysis && (
        <section className="flex flex-col gap-4 rounded-lg border border-border p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">AI 분석</h2>
            <span className="text-xs text-muted-foreground">
              {PROJECT_TYPE_LABELS[analysis.project_type ?? ""] ?? analysis.project_type}
            </span>
          </div>

          {analysis.summary && <p className="text-sm text-muted-foreground">{analysis.summary}</p>}

          {analysis.technologies.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {analysis.technologies.map((tech) => (
                <span
                  key={tech.name}
                  title={tech.evidence}
                  className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs"
                >
                  {tech.name}
                  <span className="text-muted-foreground tabular-nums">
                    {Math.round(tech.confidence * 100)}%
                  </span>
                </span>
              ))}
            </div>
          )}

          {analysis.required_roles.length > 0 && (
            <div className="text-sm">
              <span className="text-muted-foreground">필요 역할: </span>
              {analysis.required_roles.join(", ")}
            </div>
          )}

          {analysis.requirements.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground">요구사항</p>
              <ul className="mt-1 list-inside list-disc text-sm">
                {analysis.requirements.map((req) => (
                  <li key={req}>{req}</li>
                ))}
              </ul>
            </div>
          )}

          {analysis.risks.length > 0 && (
            <div>
              <p className="text-sm text-muted-foreground">리스크</p>
              <ul className="mt-1 list-inside list-disc text-sm">
                {analysis.risks.map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {opportunity.source_url && (
        <a
          href={opportunity.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="w-fit rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted"
        >
          나라장터 원문 보기 ↗
        </a>
      )}
    </div>
  );
}
