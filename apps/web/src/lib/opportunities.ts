import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

export const DEFAULT_PAGE_SIZE = 20;
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

// Only columns actually shown in the list table (apps/web/src/app/(app)/opportunities/
// page.tsx) are sortable - bid_close_at isn't a column there, so it's left out rather
// than offering a sort control for a value the table doesn't display.
export const SORT_FIELDS = ["title", "organization", "posted_at", "budget_amount"] as const;
export type SortField = (typeof SORT_FIELDS)[number];
export const DEFAULT_SORT_FIELD: SortField = "posted_at";
export const DEFAULT_SORT_DIR = "desc" as const;

export type Category = "NON_IT" | "LIKELY_IT" | "UNKNOWN";

export type OpportunitySummary = {
  id: string;
  title: string;
  category: Category;
  organization: string | null;
  budget_amount: number | null;
  posted_at: string | null;
  bid_close_at: string | null;
  matchScore: number | null;
};

export type TechnologyMatch = {
  name: string;
  confidence: number;
  evidence: string;
};

export type ProjectAnalysis = {
  status: "PENDING" | "SUCCESS" | "FAILED";
  project_type: string | null;
  technologies: TechnologyMatch[];
  required_roles: string[];
  requirements: string[];
  risks: string[];
  summary: string | null;
};

export type MatchScoreBreakdown = {
  technology_score: number;
  business_type_score: number;
  budget_score: number;
  experience_score: number;
  qualification_score: number;
  region_score: number;
  schedule_score: number;
  total_score: number;
};

export type OpportunityDetail = OpportunitySummary & {
  demand_organization: string | null;
  estimated_price: number | null;
  region_restriction: string | null;
  open_at: string | null;
  source_url: string | null;
  analysis: ProjectAnalysis | null;
  matchBreakdown: MatchScoreBreakdown | null;
};

export type OpportunityPage = {
  items: OpportunitySummary[];
  total: number;
  page: number;
  pageSize: number;
  sort: SortField;
  dir: "asc" | "desc";
};

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

// match_scores is company-scoped by RLS (see supabase/migrations - policy compares
// against auth_company_id()), so this never needs to filter by company explicitly -
// a user simply can't see another company's rows regardless of the query.
//
// Degrades gracefully on error instead of throwing: match_scores is a supplementary
// enrichment (like AI analysis), not core opportunity data - see
// docs/DATA_PIPELINE.md#failure-isolation's "shown without X, not hidden" principle. A
// match_scores-specific failure must not take down the whole opportunities list via
// error.tsx when the opportunities themselves loaded fine.
async function getMatchTotals(
  supabase: Awaited<ReturnType<typeof createClient>>,
  opportunityIds: string[],
): Promise<Map<string, number>> {
  if (opportunityIds.length === 0) return new Map();
  const { data, error } = await supabase
    .from("match_scores")
    .select("opportunity_id, total_score")
    .in("opportunity_id", opportunityIds);
  if (error) {
    console.error("Failed to load match scores, showing opportunities without them", error);
    return new Map();
  }
  return new Map((data ?? []).map((row) => [row.opportunity_id, row.total_score]));
}

export async function getOpportunities({
  page = 1,
  q,
  category,
  pageSize,
  sort,
  dir,
}: {
  page?: number;
  q?: string;
  category?: Category;
  pageSize?: number;
  sort?: string;
  dir?: string;
} = {}): Promise<OpportunityPage> {
  await requireUser();
  const supabase = await createClient();

  // Only an allow-listed set of page sizes is accepted (not an arbitrary user-supplied
  // number) - otherwise a crafted URL could request an unbounded range.
  const safePageSize = PAGE_SIZE_OPTIONS.includes(pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    ? (pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : DEFAULT_PAGE_SIZE;
  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  const from = (safePage - 1) * safePageSize;
  const to = from + safePageSize - 1;
  const safeSort = SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : DEFAULT_SORT_FIELD;
  const safeDir = dir === "asc" ? "asc" : DEFAULT_SORT_DIR;

  // opportunities_current (supabase/migrations) shows only the latest, non-cancelled
  // revision of each G2B notice thread - see docs/DATA_PIPELINE.md#notice-thread-
  // deduplication. Browsing/search/pagination all go through it instead of the raw
  // opportunities table, which keeps every historical revision.
  let query = supabase
    .from("opportunities_current")
    .select("id, title, category, organization, budget_amount, posted_at, bid_close_at", {
      count: "exact",
    })
    .order(safeSort, { ascending: safeDir === "asc", nullsFirst: false })
    .order("id", { ascending: true }) // tiebreaker for a stable order across pages
    .range(from, to);

  if (category) {
    query = query.eq("category", category);
  }

  const term = q?.trim();
  if (term) {
    const escaped = escapeLikeTerm(term);
    query = query.or(`title.ilike.%${escaped}%,organization.ilike.%${escaped}%`);
  }

  const { data, error, count } = await query;
  if (error) throw new Error(`Failed to load opportunities: ${error.message}`);

  const items = data ?? [];
  const matchTotals = await getMatchTotals(
    supabase,
    items.map((item) => item.id),
  );

  return {
    items: items.map((item) => ({ ...item, matchScore: matchTotals.get(item.id) ?? null })),
    total: count ?? 0,
    page: safePage,
    pageSize: safePageSize,
    sort: safeSort,
    dir: safeDir,
  };
}

export async function getOpportunity(id: string): Promise<OpportunityDetail | null> {
  await requireUser();
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("opportunities")
    .select(
      "id, title, category, organization, demand_organization, budget_amount, estimated_price, " +
        "region_restriction, posted_at, bid_close_at, open_at, source_url, " +
        "analysis:project_analyses(status, project_type, technologies, required_roles, requirements, risks, summary)",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load opportunity: ${error.message}`);
  if (!data) return null;

  // project_analyses has a unique(opportunity_id) constraint, so this is a true 1:1
  // relationship, but PostgREST's embed still types it as an array in the generic case.
  const raw = data as unknown as Omit<OpportunityDetail, "analysis" | "matchScore" | "matchBreakdown"> & {
    analysis: ProjectAnalysis[] | ProjectAnalysis | null;
  };
  const analysis = Array.isArray(raw.analysis) ? (raw.analysis[0] ?? null) : raw.analysis;

  const { data: matchRow, error: matchError } = await supabase
    .from("match_scores")
    .select(
      "technology_score, business_type_score, budget_score, experience_score, qualification_score, region_score, schedule_score, total_score",
    )
    .eq("opportunity_id", id)
    .maybeSingle();
  // Same failure-isolation rule as getMatchTotals above: a match_scores-specific error
  // must not hide an opportunity that otherwise loaded fine.
  if (matchError) {
    console.error("Failed to load match score, showing the opportunity without it", matchError);
  }

  return {
    ...raw,
    analysis,
    matchScore: matchRow?.total_score ?? null,
    matchBreakdown: matchRow ?? null,
  };
}
