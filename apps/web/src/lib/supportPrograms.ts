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

export async function getSupportPrograms({
  page = 1,
  q,
  status = "open",
  itOnly,
  investmentOnly,
  source,
  field,
  pageSize,
}: {
  page?: number;
  q?: string;
  status?: SupportStatus;
  itOnly?: boolean;
  investmentOnly?: boolean;
  source?: SupportSource;
  field?: SupportFieldKey;
  pageSize?: number;
} = {}): Promise<SupportProgramPage> {
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
  // support_programs_listing = support_programs + original_open/original_end for 기업마당
  // copies (supabase/migrations/20261007130000_support_programs_listing.sql).
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

  // support-display.ts의 SUPPORT_STATUSES 설명 참고. application_end는 날짜만 의미 있는
  // 값(자정)이라 Asia/Seoul 오늘 날짜와 비교한다.
  const today = seoulDateKey();
  const closingLimit = seoulDateKey(new Date(), CLOSING_SOON_DAYS);
  if (status !== "all") {
    query = query.eq("recruiting", true);
    if (status === "closing") {
      query = query.gte("application_end", today).lte("application_end", closingLimit);
    } else {
      // 검색어 조건도 .or()를 쓰지만, 두 or 파라미터는 AND로 묶인다(2026-10-07 실측).
      query = query.or(`application_end.is.null,application_end.gte.${today}`);
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

  const term = q?.trim();
  if (term) {
    query = query.or(ilikeAnyFilter(["title", "organization"], term));
  }

  // 기업마당 사본(duplicate_of가 있는 행)은 그 원본(K-Startup)이 이 보기에 지금 실제로 보일
  // 때만 숨긴다 - 원본이 안 보이는데 사본까지 숨기면 공고가 아예 사라진다.
  // - 상태 필터만 걸린 보기: 원본이 지금 모집 중이면 숨긴다. "7일 안에 마감"이면 원본 마감일도
  //   그 안이어야 한다. "마감 포함 전체"는 원본이 모집 중이면 어차피 목록에 있다.
  // - 출처·검색어·IT·투자연계·분야 조건이 있으면 숨기지 않는다. 두 행이 그 조건을 서로 다르게
  //   통과할 수 있어서다(출처 자체, 기관명·제목 표기, 분류 체계가 다르다). 이런 보기에서는
  //   같은 공고가 두 번 보이는 쪽을 택한다(2026-10-07 기준 17쌍).
  // 원본 상태는 조회 시점 값(support_programs_listing.original_open/original_end)이라, 원본이
  // 마감되면 다음 워커 실행을 기다리지 않고 바로 사본이 보인다.
  const onlyStatusFilter = !term && !itOnly && !investmentOnly && !fieldGroup && !source;
  if (onlyStatusFilter) {
    query =
      status === "closing"
        ? query.or(
            `duplicate_of.is.null,original_open.is.false,original_end.is.null,original_end.lt.${today},original_end.gt.${closingLimit}`,
          )
        : query.or("duplicate_of.is.null,original_open.is.false");
  }

  const { data, error, count } = await query;
  if (error) throw new Error(`Failed to load support programs: ${error.message}`);

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
    .from("support_programs")
    .select(
      "id, source, title, organization, supervising_type, category, region, recruiting, investment_linked, it_related, application_end, application_period_text, department, target, application_start, description, source_url",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load support program: ${error.message}`);
  return data;
}
