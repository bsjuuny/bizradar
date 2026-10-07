import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";
import { seoulDateKey } from "@/lib/format";
import { ilikeAnyFilter } from "@/lib/postgrest";
import {
  CLOSING_SOON_DAYS,
  type SupportFieldKey,
  type SupportSource,
  type SupportStatus,
  parseSupportField,
} from "@/lib/support-display";
import { copyHidingFilter } from "@/lib/support-filters";

export const DEFAULT_PAGE_SIZE = 20;
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

export type SupportProgramSummary = {
  id: string;
  source: SupportSource;
  title: string;
  organization: string | null;
  supervising_type: string | null;
  category: string | null;
  region: string | null;
  recruiting: boolean | null;
  investment_linked: boolean;
  it_related: boolean;
  application_end: string | null;
  application_period_text: string | null;
};

export type SupportProgramDetail = SupportProgramSummary & {
  /** support_program_is_open() - the one definition of 모집 중 the list filters on. */
  is_open: boolean;
  department: string | null;
  target: string | null;
  application_start: string | null;
  description: string | null;
  source_url: string | null;
};

export type SupportProgramPage = {
  items: SupportProgramSummary[];
  total: number;
  page: number;
  pageSize: number;
};

export type SupportProgramQuery = {
  page?: number;
  q?: string;
  status?: SupportStatus;
  itOnly?: boolean;
  investmentOnly?: boolean;
  source?: SupportSource;
  field?: SupportFieldKey;
  pageSize?: number;
};

export async function getSupportPrograms(
  options: SupportProgramQuery = {},
): Promise<SupportProgramPage> {
  const { page = 1, q, status = "open", itOnly, investmentOnly, source, field, pageSize } = options;
  await requireUser();
  const supabase = await createClient();

  const safePageSize = PAGE_SIZE_OPTIONS.includes(pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    ? (pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : DEFAULT_PAGE_SIZE;
  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  const from = (safePage - 1) * safePageSize;
  const to = from + safePageSize - 1;

  // A single non-concatenated string literal, not a `const` built from `+` - Supabase's
  // generated types compute the return shape from the literal select string itself, and
  // TS widens any `+`-concatenated or variable-referenced string to plain `string`,
  // which breaks that inference (`GenericStringError` - same gotcha hit and documented
  // in apps/web/src/lib/opportunities.ts).
  // support_programs_listing = support_programs + is_open, and for 기업마당 copies the
  // original's current state and filter columns (original_*) -
  // supabase/migrations/20261007130000_support_programs_listing.sql.
  let query = supabase
    .from("support_programs_listing")
    .select(
      "id, source, title, organization, supervising_type, category, region, recruiting, investment_linked, it_related, application_end, application_period_text",
      { count: "exact" },
    )
    // `recruiting` (rcrt_prgs_yn) first - found live: sorting by application_end
    // ascending alone put already-expired programs first (the oldest, longest-past
    // deadlines sort "smallest"), not soonest-still-open ones. `recruiting: true` rows
    // sort before `false`/null, and *within* recruiting=true, ascending application_end
    // correctly means "closing soonest first."
    .order("recruiting", { ascending: false, nullsFirst: false })
    .order("application_end", { ascending: true, nullsFirst: false })
    .order("id", { ascending: true })
    .range(from, to);

  // "모집 중"은 DB의 is_open(support_program_is_open) 하나로 정한다 - 워커의 중복 짝짓기도
  // 같은 정의를 쓴다. "7일 안에 마감"은 그중 마감일이 Asia/Seoul 오늘부터 7일 안인 것.
  // application_end는 날짜만 의미 있는 값(자정)이라 날짜 문자열과 비교한다.
  const today = seoulDateKey();
  const closingLimit = seoulDateKey(new Date(), CLOSING_SOON_DAYS);
  if (status !== "all") {
    query = query.eq("is_open", true);
    if (status === "closing") {
      query = query.gte("application_end", today).lte("application_end", closingLimit);
    }
  }

  if (itOnly) {
    query = query.eq("it_related", true);
  }

  if (investmentOnly) {
    query = query.eq("investment_linked", true);
  }

  const fieldGroup = parseSupportField(field);
  if (fieldGroup) {
    query = query.in("category", [...fieldGroup.categories]);
  }

  if (source) {
    query = query.eq("source", source);
  }

  const term = q?.trim() || undefined;
  if (term) {
    query = query.or(ilikeAnyFilter(["title", "organization"], term));
  }

  // 기업마당 사본은 원본(K-Startup)도 이 보기의 조건을 모두 통과해 함께 나올 때만 숨긴다 -
  // 그렇지 않으면 공고가 아예 사라진다. 원본 쪽 조건은 조회 시점 값(original_*)으로 평가한다.
  // 검색어 조건과 이 조건 모두 .or()를 쓰지만, 두 or 파라미터는 AND로 묶인다(2026-10-07 실측).
  const hiding = copyHidingFilter({
    status,
    itOnly: Boolean(itOnly),
    investmentOnly: Boolean(investmentOnly),
    source,
    categories: fieldGroup?.categories,
    term,
    today,
    closingLimit,
  });
  if (hiding) {
    query = query.or(hiding);
  }

  const { data, error, count } = await query;
  if (error) {
    // A page past the end (an old link, or the list got shorter) - PostgREST answers 416
    // PGRST103 instead of an empty page. Show the first page rather than an error.
    if (error.code === "PGRST103" && safePage > 1) {
      return getSupportPrograms({ ...options, page: 1 });
    }
    throw new Error(`Failed to load support programs: ${error.message}`);
  }

  return {
    items: data ?? [],
    total: count ?? 0,
    page: safePage,
    pageSize: safePageSize,
  };
}

export async function getSupportProgram(id: string): Promise<SupportProgramDetail | null> {
  await requireUser();
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("support_programs_listing")
    .select(
      "id, source, title, organization, supervising_type, category, region, recruiting, is_open, investment_linked, it_related, application_end, application_period_text, department, target, application_start, description, source_url",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load support program: ${error.message}`);
  return data;
}
