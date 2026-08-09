import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

// PostgREST caps a single request's rows even with no explicit .limit() - paginate
// past it rather than silently truncating once IT-classified opportunities exceed it.
const FETCH_PAGE_SIZE = 1000;

export type YesNoUnknownCounts = { yes: number; no: number; unknown: number };

export type NamedCount = { name: string; count: number };

export type MarketStats = {
  totalItOpportunities: number;
  industryLimited: YesNoUnknownCounts;
  participationLimited: YesNoUnknownCounts;
  regionRestricted: { restricted: number; unrestricted: number };
  topRegionRestrictions: NamedCount[];
  topProcurementCategories: NamedCount[];
  topRequiredQualifications: NamedCount[];
  experienceYearsDistribution: NamedCount[];
  analyzedCount: number;
};

async function fetchAllRows<T>(
  query: (
    from: number,
    to: number,
  ) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>,
): Promise<T[]> {
  const rows: T[] = [];
  let from = 0;
  for (;;) {
    const { data, error } = await query(from, from + FETCH_PAGE_SIZE - 1);
    if (error) throw new Error(`Failed to load market stats data: ${error.message}`);
    if (!data || data.length === 0) break;
    rows.push(...data);
    if (data.length < FETCH_PAGE_SIZE) break;
    from += FETCH_PAGE_SIZE;
  }
  return rows;
}

function tallyYesNoUnknown(values: (boolean | null)[]): YesNoUnknownCounts {
  const counts: YesNoUnknownCounts = { yes: 0, no: 0, unknown: 0 };
  for (const v of values) {
    if (v === true) counts.yes += 1;
    else if (v === false) counts.no += 1;
    else counts.unknown += 1;
  }
  return counts;
}

function topCounts(values: (string | null)[], limit: number): NamedCount[] {
  const counts = new Map<string, number>();
  for (const v of values) {
    if (!v) continue;
    counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

// Statistics over IT-classified (category=LIKELY_IT) *current* opportunities only (see
// docs/DATA_PIPELINE.md#notice-thread-deduplication) - a superseded/cancelled notice
// revision shouldn't skew "what does the current IT bid market actually require".
export async function getMarketStats(): Promise<MarketStats> {
  await requireUser();
  const supabase = await createClient();

  const opportunities = await fetchAllRows<{
    id: string;
    industry_limited: boolean | null;
    participation_limited: boolean | null;
    region_restriction: string | null;
    procurement_category: string | null;
  }>((from, to) =>
    supabase
      .from("opportunities_current")
      .select("id, industry_limited, participation_limited, region_restriction, procurement_category")
      .eq("category", "LIKELY_IT")
      .range(from, to),
  );

  const ids = opportunities.map((o) => o.id);
  const analyses =
    ids.length === 0
      ? []
      : await fetchAllRows<{
          opportunity_id: string;
          min_experience_years: number | null;
          required_qualifications: string[] | null;
        }>((from, to) =>
          supabase
            .from("project_analyses")
            .select("opportunity_id, min_experience_years, required_qualifications")
            .eq("status", "SUCCESS")
            .in("opportunity_id", ids)
            .range(from, to),
        );

  const restricted = opportunities.filter((o) => (o.region_restriction ?? "").trim().length > 0);

  const allQualifications = analyses.flatMap((a) => a.required_qualifications ?? []);

  return {
    totalItOpportunities: opportunities.length,
    industryLimited: tallyYesNoUnknown(opportunities.map((o) => o.industry_limited)),
    participationLimited: tallyYesNoUnknown(opportunities.map((o) => o.participation_limited)),
    regionRestricted: {
      restricted: restricted.length,
      unrestricted: opportunities.length - restricted.length,
    },
    topRegionRestrictions: topCounts(
      restricted.map((o) => o.region_restriction),
      8,
    ),
    topProcurementCategories: topCounts(
      opportunities.map((o) => o.procurement_category),
      10,
    ),
    topRequiredQualifications: topCounts(allQualifications, 10),
    // Sorted by year value (not frequency, unlike the other breakdowns above) - a
    // distribution reads naturally low-to-high, "명시 안 됨" first.
    experienceYearsDistribution: experienceYearsDistribution(analyses.map((a) => a.min_experience_years)),
    analyzedCount: analyses.length,
  };
}

function experienceYearsDistribution(values: (number | null)[]): NamedCount[] {
  const counts = new Map<number | null, number>();
  for (const v of values) {
    counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => (a[0] ?? -1) - (b[0] ?? -1))
    .map(([years, count]) => ({
      name: years == null ? "명시 안 됨" : `${years}년 이상`,
      count,
    }));
}
