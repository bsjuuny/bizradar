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
