import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

export const DEFAULT_PAGE_SIZE = 20;
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

export const SORT_FIELDS = ["awarded_at", "award_amount", "award_rate", "participant_count"] as const;
export type SortField = (typeof SORT_FIELDS)[number];
export const DEFAULT_SORT_FIELD: SortField = "awarded_at";
export const DEFAULT_SORT_DIR = "desc" as const;

export type AwardResultSummary = {
  id: string;
  bid_ntce_no: string;
  bid_ntce_ord: number;
  title: string | null;
  winner_name: string;
  award_amount: number | null;
  award_rate: number | null;
  planned_price: number | null;
  participant_count: number | null;
  opened_at: string | null;
  awarded_at: string | null;
  // Not every award result has a matching row in opportunities_current - the
  // collector only tracks IT-relevant/recent notices, award results cover the full
  // G2B firehose - so this links through when available and is null otherwise.
  opportunityId: string | null;
};

export type AwardResultPage = {
  items: AwardResultSummary[];
  total: number;
  page: number;
  pageSize: number;
  sort: SortField;
  dir: "asc" | "desc";
};

export type OrganizationWinner = {
  winnerName: string;
  winCount: number;
  totalAwardAmount: number;
  mostRecentAwardedAt: string | null;
};

const ORGANIZATION_HISTORY_NOTICE_LIMIT = 200;

/**
 * "이 발주처에서 최근 자주 이기는 회사" - g2b_award_results 자체에는 organization이
 * 없어서(공고 쪽에만 있음), opportunities_current로 같은 organization의 공고 번호를 먼저
 * 찾은 뒤 award_results를 그 번호들로 조회해 승자별로 집계한다. 새 뷰/마이그레이션 없이
 * 기존 두 테이블만으로 계산 - 조직당 공고 수가 큰 경우를 대비해 최근 N건으로 상한을 둔다.
 */
export async function getOrganizationAwardHistory(
  organization: string,
  options: { excludeBidNtceNo?: string | null; limit?: number } = {},
): Promise<OrganizationWinner[]> {
  await requireUser();
  if (!organization.trim()) return [];
  const supabase = await createClient();

  let noticesQuery = supabase
    .from("opportunities_current")
    .select("bid_ntce_no, bid_ntce_ord")
    .eq("organization", organization)
    .order("posted_at", { ascending: false, nullsFirst: false })
    .limit(ORGANIZATION_HISTORY_NOTICE_LIMIT);
  if (options.excludeBidNtceNo) {
    noticesQuery = noticesQuery.neq("bid_ntce_no", options.excludeBidNtceNo);
  }

  const { data: notices, error: noticesError } = await noticesQuery;
  if (noticesError) {
    console.error("Failed to load notices for organization award history", noticesError);
    return [];
  }
  if (!notices || notices.length === 0) return [];

  const bidNtceNos = [...new Set(notices.map((n) => n.bid_ntce_no).filter((v): v is string => v !== null))];
  if (bidNtceNos.length === 0) return [];
  // opportunities_current의 (bid_ntce_no, bid_ntce_ord) 조합만 승자 집계에 넣는다 - bid_ntce_no만
  // 필터하면 같은 스레드의 유찰/재공고 등 다른 차수 낙찰 결과까지 섞여 승수가 부풀 수 있다.
  const validNoticeKeys = new Set(notices.map((n) => `${n.bid_ntce_no}:${n.bid_ntce_ord}`));

  const { data: awards, error: awardsError } = await supabase
    .from("g2b_award_results")
    .select("winner_name, award_amount, awarded_at, bid_ntce_no, bid_ntce_ord")
    .in("bid_ntce_no", bidNtceNos);
  if (awardsError) {
    console.error("Failed to load award results for organization award history", awardsError);
    return [];
  }

  const byWinner = new Map<string, OrganizationWinner>();
  for (const row of awards ?? []) {
    if (!validNoticeKeys.has(`${row.bid_ntce_no}:${row.bid_ntce_ord}`)) continue;
    const existing = byWinner.get(row.winner_name) ?? {
      winnerName: row.winner_name,
      winCount: 0,
      totalAwardAmount: 0,
      mostRecentAwardedAt: null,
    };
    existing.winCount += 1;
    existing.totalAwardAmount += row.award_amount ?? 0;
    if (!existing.mostRecentAwardedAt || (row.awarded_at && row.awarded_at > existing.mostRecentAwardedAt)) {
      existing.mostRecentAwardedAt = row.awarded_at;
    }
    byWinner.set(row.winner_name, existing);
  }

  return [...byWinner.values()]
    .sort((a, b) => b.winCount - a.winCount || b.totalAwardAmount - a.totalAwardAmount)
    .slice(0, options.limit ?? 5);
}

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

// Batch-maps (bid_ntce_no, bid_ntce_ord) back to an opportunities_current.id so a row
// can link to its opportunity detail page. Degrades to "no link" per row on error or
// on a genuine miss, rather than hiding the award row itself - same failure-isolation
// rule as getMatchTotals in lib/opportunities.ts.
async function getOpportunityIdsByNotice(
  supabase: Awaited<ReturnType<typeof createClient>>,
  notices: { bid_ntce_no: string; bid_ntce_ord: number }[],
): Promise<Map<string, string>> {
  if (notices.length === 0) return new Map();
  const noticeNumbers = [...new Set(notices.map((n) => n.bid_ntce_no))];
  const { data, error } = await supabase
    .from("opportunities_current")
    .select("id, bid_ntce_no, bid_ntce_ord")
    .in("bid_ntce_no", noticeNumbers);
  if (error) {
    console.error("Failed to map award results to opportunities, showing without links", error);
    return new Map();
  }
  return new Map((data ?? []).map((row) => [`${row.bid_ntce_no}:${row.bid_ntce_ord}`, row.id]));
}

// Data itself isn't company-scoped (g2b_award_results is public G2B data, same RLS
// shape as opportunities_current - any authenticated user can already read it), so
// this only requires a logged-in user. The BizRadar-operator-only restriction is
// enforced by requireAdmin() in the page component, same split as lib/market.ts.
export async function getAwardResults({
  page = 1,
  q,
  pageSize,
  sort,
  dir,
}: {
  page?: number;
  q?: string;
  pageSize?: number;
  sort?: string;
  dir?: string;
} = {}): Promise<AwardResultPage> {
  await requireUser();
  const supabase = await createClient();

  const safePageSize = PAGE_SIZE_OPTIONS.includes(pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    ? (pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : DEFAULT_PAGE_SIZE;
  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  const from = (safePage - 1) * safePageSize;
  const to = from + safePageSize - 1;
  const safeSort = SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : DEFAULT_SORT_FIELD;
  const safeDir = dir === "asc" ? "asc" : DEFAULT_SORT_DIR;

  let query = supabase
    .from("g2b_award_results")
    .select(
      "id, bid_ntce_no, bid_ntce_ord, title, winner_name, award_amount, award_rate, planned_price, participant_count, opened_at, awarded_at",
      { count: "exact" },
    )
    .order(safeSort, { ascending: safeDir === "asc", nullsFirst: false })
    .order("id", { ascending: true }) // tiebreaker for a stable order across pages
    .range(from, to);

  const term = q?.trim();
  if (term) {
    const escaped = escapeLikeTerm(term);
    query = query.or(`title.ilike.%${escaped}%,winner_name.ilike.%${escaped}%`);
  }

  const { data, error, count } = await query;
  if (error) throw new Error(`Failed to load award results: ${error.message}`);

  const items = data ?? [];
  const opportunityIds = await getOpportunityIdsByNotice(supabase, items);

  return {
    items: items.map((item) => ({
      ...item,
      opportunityId: opportunityIds.get(`${item.bid_ntce_no}:${item.bid_ntce_ord}`) ?? null,
    })),
    total: count ?? 0,
    page: safePage,
    pageSize: safePageSize,
    sort: safeSort,
    dir: safeDir,
  };
}
