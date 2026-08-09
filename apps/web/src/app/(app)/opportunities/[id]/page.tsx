import Link from "next/link";
import { notFound } from "next/navigation";
import { getOpportunity } from "@/lib/opportunities";
import { formatCurrencyKRW, formatDateTime } from "@/lib/format";
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

      {opportunity.matchBreakdown && (
        <section className="rounded-lg border border-border p-5">
          <h2 className="text-sm font-semibold">Company Match</h2>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            {(
              [
                ["기술", opportunity.matchBreakdown.technology_score, 30],
                ["사업 형태", opportunity.matchBreakdown.business_type_score, 20],
                ["예산", opportunity.matchBreakdown.budget_score, 15],
                ["경력", opportunity.matchBreakdown.experience_score, 15],
                ["자격/인증", opportunity.matchBreakdown.qualification_score, 10],
                ["지역", opportunity.matchBreakdown.region_score, 5],
                ["일정", opportunity.matchBreakdown.schedule_score, 5],
              ] as const
            ).map(([label, score, max]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="tabular-nums">
                  {Math.round(score)} / {max}
                </dd>
              </div>
            ))}
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
