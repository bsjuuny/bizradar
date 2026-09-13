import "server-only";

import { requireCompany, requireUser } from "@/lib/dal";
import { createClient } from "@/lib/supabase/server";
import type { OpportunitySummary } from "@/lib/opportunities";
import { matchesWatch, type WatchCondition } from "@/lib/queue";

/**
 * "Watch 다이제스트": 이메일/슬랙 발송 인프라(공급자 API 키 등)가 이 프로젝트에 아직
 * 없어서, 우선은 대시보드에서 바로 보이는 인앱 다이제스트로 구현한다. 최근 게시된
 * 공고 중 활성 Watch 조건에 걸리는 것만 모아서 보여준다 - 매일 로그인해서 전체
 * Project Radar를 훑지 않아도 되게 하는 게 목적.
 */
const DIGEST_WINDOW_HOURS = 24;
const DIGEST_LOOKBACK_LIMIT = 200;

export type DigestMatch = {
  opportunity: OpportunitySummary;
  watchNames: string[];
};

export type WatchDigest = {
  windowHours: number;
  activeWatchCount: number;
  matches: DigestMatch[];
};

export async function getWatchDigest(): Promise<WatchDigest> {
  await requireUser();
  const { company } = await requireCompany();
  const supabase = await createClient();

  const { data: watchRows, error: watchError } = await supabase
    .from("watch_conditions")
    .select("id, name, keyword, category, min_budget, max_budget, min_match_score, active")
    .eq("company_id", company.id)
    .eq("active", true);
  if (watchError) throw new Error(`Failed to load watch conditions: ${watchError.message}`);

  const watches = (watchRows ?? []) as WatchCondition[];
  if (watches.length === 0) {
    return { windowHours: DIGEST_WINDOW_HOURS, activeWatchCount: 0, matches: [] };
  }

  const since = new Date(Date.now() - DIGEST_WINDOW_HOURS * 60 * 60 * 1000).toISOString();
  const { data: opportunities, error: opportunityError } = await supabase
    .from("opportunities_current")
    .select("id, title, category, organization, budget_amount, posted_at, bid_close_at")
    .gte("posted_at", since)
    .order("posted_at", { ascending: false })
    .limit(DIGEST_LOOKBACK_LIMIT);
  if (opportunityError) throw new Error(`Failed to load recent opportunities: ${opportunityError.message}`);

  const ids = (opportunities ?? []).map((item) => item.id);
  const { data: matchRows, error: matchError } = ids.length
    ? await supabase.from("match_scores").select("opportunity_id, total_score").in("opportunity_id", ids)
    : { data: [], error: null };
  if (matchError) {
    console.error("Failed to load match scores for digest", matchError);
  }
  const matchById = new Map((matchRows ?? []).map((row) => [row.opportunity_id, row.total_score as number]));

  const matches: DigestMatch[] = [];
  for (const item of (opportunities ?? []) as Omit<OpportunitySummary, "matchScore">[]) {
    const matchScore = matchById.get(item.id) ?? null;
    const summary: OpportunitySummary = { ...item, matchScore };
    const watchNames = watches.filter((watch) => matchesWatch(summary, watch, matchScore)).map((w) => w.name);
    if (watchNames.length > 0) matches.push({ opportunity: summary, watchNames });
  }

  return { windowHours: DIGEST_WINDOW_HOURS, activeWatchCount: watches.length, matches };
}
