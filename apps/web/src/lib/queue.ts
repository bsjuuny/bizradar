import "server-only";

import { requireCompany, requireUser } from "@/lib/dal";
import { createClient } from "@/lib/supabase/server";
import type { Category, OpportunitySummary } from "@/lib/opportunities";

export type QueueStatus = "REVIEWING" | "RESPONDING" | "ON_HOLD" | "DECLINED";

export type SavedOpportunity = {
  opportunity_id: string;
  status: QueueStatus;
  owner_name: string | null;
  note: string | null;
  updated_at: string;
};

export type WatchCondition = {
  id: string;
  name: string;
  keyword: string | null;
  category: Category | null;
  min_budget: number | null;
  max_budget: number | null;
  min_match_score: number | null;
  active: boolean;
};

export type QueueItem = OpportunitySummary & {
  saved: SavedOpportunity | null;
  watchMatches: string[];
};

export type TodayQueue = {
  items: QueueItem[];
  savedCount: number;
  respondingCount: number;
  watchConditions: WatchCondition[];
};

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

function matchesWatch(
  opportunity: OpportunitySummary,
  watch: WatchCondition,
  matchScore: number | null,
) {
  if (!watch.active) return false;
  if (watch.category && opportunity.category !== watch.category) return false;
  if (watch.min_budget !== null && (opportunity.budget_amount ?? 0) < watch.min_budget) return false;
  if (watch.max_budget !== null && opportunity.budget_amount !== null && opportunity.budget_amount > watch.max_budget) {
    return false;
  }
  if (watch.min_match_score !== null && (matchScore ?? 0) < watch.min_match_score) return false;
  const keyword = watch.keyword?.trim().toLowerCase();
  if (keyword) {
    const haystack = `${opportunity.title} ${opportunity.organization ?? ""}`.toLowerCase();
    if (!haystack.includes(keyword)) return false;
  }
  return true;
}

export async function getTodayQueue(): Promise<TodayQueue> {
  await requireUser();
  const { company } = await requireCompany();
  const supabase = await createClient();

  const { data: opportunities, error: opportunityError } = await supabase
    .from("opportunities_current")
    .select("id, title, category, organization, budget_amount, posted_at, bid_close_at")
    .order("bid_close_at", { ascending: true, nullsFirst: false })
    .limit(80);
  if (opportunityError) throw new Error(`Failed to load queue opportunities: ${opportunityError.message}`);

  const ids = (opportunities ?? []).map((item) => item.id);

  const { data: matchRows, error: matchError } = ids.length
    ? await supabase.from("match_scores").select("opportunity_id, total_score").in("opportunity_id", ids)
    : { data: [], error: null };
  if (matchError) {
    console.error("Failed to load match scores for queue", matchError);
  }

  const { data: savedRows, error: savedError } = ids.length
    ? await supabase
        .from("saved_opportunities")
        .select("opportunity_id, status, owner_name, note, updated_at")
        .eq("company_id", company.id)
        .in("opportunity_id", ids)
    : { data: [], error: null };
  if (savedError) throw new Error(`Failed to load saved opportunities: ${savedError.message}`);

  const { data: watchRows, error: watchError } = await supabase
    .from("watch_conditions")
    .select("id, name, keyword, category, min_budget, max_budget, min_match_score, active")
    .eq("company_id", company.id)
    .order("created_at", { ascending: false });
  if (watchError) throw new Error(`Failed to load watch conditions: ${watchError.message}`);

  const matchById = new Map((matchRows ?? []).map((row) => [row.opportunity_id, row.total_score as number]));
  const savedById = new Map((savedRows ?? []).map((row) => [row.opportunity_id, row as SavedOpportunity]));
  const watches = (watchRows ?? []) as WatchCondition[];

  const items = ((opportunities ?? []) as Omit<OpportunitySummary, "matchScore">[])
    .map((item) => {
      const matchScore = matchById.get(item.id) ?? null;
      const summary: OpportunitySummary = { ...item, matchScore };
      return {
        ...summary,
        saved: savedById.get(item.id) ?? null,
        watchMatches: watches
          .filter((watch) => matchesWatch(summary, watch, matchScore))
          .map((watch) => watch.name),
      };
    })
    .sort((a, b) => {
      const aSaved = a.saved ? 1 : 0;
      const bSaved = b.saved ? 1 : 0;
      if (aSaved !== bSaved) return bSaved - aSaved;
      const aMatch = a.matchScore ?? -1;
      const bMatch = b.matchScore ?? -1;
      if (aMatch !== bMatch) return bMatch - aMatch;
      return String(a.bid_close_at ?? "9999").localeCompare(String(b.bid_close_at ?? "9999"));
    });

  return {
    items,
    savedCount: savedRows?.length ?? 0,
    respondingCount: (savedRows ?? []).filter((row) => row.status === "RESPONDING").length,
    watchConditions: watches,
  };
}

export async function getWatchPreview(keyword: string) {
  await requireUser();
  const supabase = await createClient();
  const term = keyword.trim();
  if (!term) return [];
  const escaped = escapeLikeTerm(term);
  const { data, error } = await supabase
    .from("opportunities_current")
    .select("id, title, category, organization, budget_amount, posted_at, bid_close_at")
    .or(`title.ilike.%${escaped}%,organization.ilike.%${escaped}%`)
    .order("bid_close_at", { ascending: true, nullsFirst: false })
    .limit(10);
  if (error) throw new Error(`Failed to preview watch condition: ${error.message}`);
  return data ?? [];
}
