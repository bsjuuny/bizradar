import Link from "next/link";
import { notFound } from "next/navigation";
import { getOpportunity } from "@/lib/opportunities";
import { formatCurrencyKRW, formatDateTime } from "@/lib/format";

export default async function OpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const opportunity = await getOpportunity(id);
  if (!opportunity) notFound();

  return (
    <div className="flex flex-col gap-6">
      <Link href="/opportunities" className="text-sm text-muted-foreground hover:underline">
        ← Project Radar 목록으로
      </Link>

      <h1 className="text-xl font-semibold text-balance">{opportunity.title}</h1>

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
