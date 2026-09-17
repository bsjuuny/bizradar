import "server-only";

import { requireCompany, requireUser } from "@/lib/dal";
import { createClient } from "@/lib/supabase/server";
import {
  OPPORTUNITY_SUMMARY_COLUMNS,
  type Category,
  type OpportunitySummary,
} from "@/lib/opportunities";
import { daysUntilDeadline, formatCurrencyKRW } from "@/lib/format";

/** 이 안이면 "오늘 결정해야 할" 긴급 항목으로 취급한다 (D-3 ~ D-Day). */
const URGENT_WINDOW_DAYS = 3;

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
  /** 이 공고의 나라장터 리비전이 바뀌면서 마감일/예산/지역제한이 달라졌는지. */
  hasRevisionChange: boolean;
};

export type TodayQueue = {
  items: QueueItem[];
  /** bid_close_at이 오늘부터 D-3 이내이고 아직 DECLINED로 정리되지 않은 항목. */
  urgentItems: QueueItem[];
  savedCount: number;
  respondingCount: number;
  watchConditions: WatchCondition[];
};

function isUrgent(item: QueueItem, now: Date): boolean {
  if (item.saved?.status === "DECLINED") return false;
  const days = daysUntilDeadline(item.bid_close_at, now);
  return days !== null && days >= 0 && days <= URGENT_WINDOW_DAYS;
}

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

export function matchesWatch(
  opportunity: OpportunitySummary,
  watch: WatchCondition,
  matchScore: number | null,
) {
  if (!watch.active) return false;
  if (!hasWatchCriteria(watch)) return false;
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

type WatchCriteriaFields = Pick<
  WatchCondition,
  "keyword" | "category" | "min_budget" | "max_budget" | "min_match_score"
>;

/**
 * Watch 조건을 사람이 읽을 요약 조각들로 바꾼다. 빈 배열이면 진짜로 조건이 하나도 없는
 * Watch다(= `hasWatchCriteria`가 false).
 *
 * `hasWatchCriteria`가 조건으로 인정하는 필드를 하나도 빠뜨리지 말 것 - 큐 페이지가
 * keyword/category/min_match_score만 직접 나열하고 예산 두 필드를 빼먹어서, 예산만
 * 설정한 활성 Watch가 "설정된 필터 없음"으로 표시되던 버그가 있었다. 실제로는 정상
 * 매칭되고 알림도 나가는 Watch였다. 두 함수가 같은 필드 목록(WatchCriteriaFields)을
 * 공유하게 묶어 두면 다음에 조건이 추가될 때 한쪽만 고치는 실수가 타입에서 드러난다.
 */
export function describeWatchCriteria(watch: WatchCriteriaFields): string[] {
  const parts: string[] = [];
  const keyword = watch.keyword?.trim();
  if (keyword) parts.push(`키워드: ${keyword}`);
  if (watch.category) parts.push(`분류: ${watch.category}`);
  if (watch.min_budget !== null && watch.max_budget !== null) {
    parts.push(
      `예산: ${formatCurrencyKRW(watch.min_budget)} ~ ${formatCurrencyKRW(watch.max_budget)}`,
    );
  } else if (watch.min_budget !== null) {
    parts.push(`예산: ${formatCurrencyKRW(watch.min_budget)} 이상`);
  } else if (watch.max_budget !== null) {
    parts.push(`예산: ${formatCurrencyKRW(watch.max_budget)} 이하`);
  }
  if (watch.min_match_score !== null) parts.push(`매칭점수: ${watch.min_match_score}점 이상`);
  return parts;
}

export function hasWatchCriteria(watch: WatchCriteriaFields) {
  return Boolean(
    watch.keyword?.trim() ||
      watch.category ||
      watch.min_budget !== null ||
      watch.max_budget !== null ||
      watch.min_match_score !== null,
  );
}

const REVISION_CHANGE_FIELDS = ["bid_close_at", "budget_amount", "region_restriction", "open_at"] as const;

/**
 * 큐에 보이는 공고 중 마감일/예산/지역제한이 바뀐(리비전이 올라간) 것의 id 집합을 계산한다.
 * 공고당 별도 쿼리를 날리면 큐 페이지 로드마다 최대 80번의 추가 쿼리가 나가므로, 관련된
 * bid_ntce_no를 한 번에 모아 opportunities 원본 테이블에서 그 리비전들만 한 번에 가져와
 * 메모리에서 비교한다(N+1 방지).
 */
async function getRevisionChangedIds(
  supabase: Awaited<ReturnType<typeof createClient>>,
  opportunities: { id: string; bid_ntce_no: string | null; bid_ntce_ord: number | null }[],
): Promise<Set<string>> {
  // G2B 원본 차수는 0부터 시작한다(최초 등록공고 = 0, 첫 정정/변경공고 = 1 - 아래
  // worker/tests/test_g2b_collector.py에서 확인). ord=0이면 비교할 이전 리비전이
  // 없으므로 그때만 건너뛴다.
  const candidates = opportunities.filter(
    (o): o is { id: string; bid_ntce_no: string; bid_ntce_ord: number } =>
      o.bid_ntce_no !== null && o.bid_ntce_ord !== null && o.bid_ntce_ord > 0,
  );
  if (candidates.length === 0) return new Set();

  const bidNtceNos = [...new Set(candidates.map((c) => c.bid_ntce_no))];
  const { data: revisions, error } = await supabase
    .from("opportunities")
    .select("bid_ntce_no, bid_ntce_ord, bid_close_at, budget_amount, region_restriction, open_at")
    .in("bid_ntce_no", bidNtceNos);
  if (error) {
    console.error("Failed to load notice revisions for change detection", error);
    return new Set();
  }

  const byThread = new Map<string, typeof revisions>();
  for (const row of revisions ?? []) {
    const list = byThread.get(row.bid_ntce_no) ?? [];
    list.push(row);
    byThread.set(row.bid_ntce_no, list);
  }

  const changedIds = new Set<string>();
  for (const candidate of candidates) {
    const thread = (byThread.get(candidate.bid_ntce_no) ?? []).slice().sort((a, b) => a.bid_ntce_ord - b.bid_ntce_ord);
    const currentIndex = thread.findIndex((r) => r.bid_ntce_ord === candidate.bid_ntce_ord);
    if (currentIndex <= 0) continue; // no earlier revision in the fetched set
    const current = thread[currentIndex];
    const previous = thread[currentIndex - 1];
    const changed = REVISION_CHANGE_FIELDS.some((field) => current[field] !== previous[field]);
    if (changed) changedIds.add(candidate.id);
  }
  return changedIds;
}

export async function getTodayQueue(): Promise<TodayQueue> {
  await requireUser();
  const { company } = await requireCompany();
  const supabase = await createClient();
  const now = new Date();

  // opportunities_current는 마감이 지난 공고를 걸러 주지 않는다(취소공고만 제외). 마감일
  // 오름차순으로 80건만 가져오면 과거에 마감된 공고가 아직 많이 쌓여 있을 때 그것들이
  // 창을 채워 버려서 정작 다가오는 마감은 하나도 안 보이는 문제가 생긴다(실 데이터로 확인:
  // 14,453건 중 상위 80건이 전부 몇 달 전에 이미 마감된 건이었음). 마감일이 아직 안
  // 지났거나(오늘 포함) 아예 정해지지 않은 공고만 가져온다.
  const { data: opportunities, error: opportunityError } = await supabase
    .from("opportunities_current")
    .select(`${OPPORTUNITY_SUMMARY_COLUMNS}, bid_ntce_no, bid_ntce_ord`)
    .or(`bid_close_at.gte.${now.toISOString()},bid_close_at.is.null`)
    .order("bid_close_at", { ascending: true, nullsFirst: false })
    .limit(80);
  if (opportunityError) throw new Error(`Failed to load queue opportunities: ${opportunityError.message}`);

  const ids = (opportunities ?? []).map((item) => item.id);
  const revisionChangedIds = await getRevisionChangedIds(supabase, opportunities ?? []);

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
        hasRevisionChange: revisionChangedIds.has(item.id),
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

  const urgentItems = items
    .filter((item) => isUrgent(item, now))
    .sort((a, b) => String(a.bid_close_at ?? "9999").localeCompare(String(b.bid_close_at ?? "9999")));

  return {
    items,
    urgentItems,
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
