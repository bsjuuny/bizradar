import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";
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
  /**
   * is_open(support_programs) in SQL - the one definition of 모집 중. null = unknown: the
   * source gave neither a 모집 status nor a deadline (shown as "—", never as 마감).
   */
  is_open: boolean | null;
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
  /** The page actually shown - can differ from the one asked for (see below). */
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

type ListResult = { total: number; items: SupportProgramSummary[] };

/** Far past any real list (100,000 pages); keeps (page - 1) * pageSize within int4. */
const MAX_PAGE = 100_000;

/**
 * Filtering, hiding 기업마당 copies whose K-Startup original is in the same result,
 * ordering and paging all happen in one SQL function, list_support_programs
 * (supabase/migrations/20261007130000_support_programs_listing.sql, replaced by
 * 20261008100000_support_programs_open_follows_original.sql) - so the rule "hide a
 * copy only when its original is listed too" can't drift from the filters, and "모집 중"
 * has a single definition (the is_open(support_programs) SQL function).
 */
export async function getSupportPrograms(
  options: SupportProgramQuery = {},
): Promise<SupportProgramPage> {
  await requireUser();
  const supabase = await createClient();

  const pageSize = PAGE_SIZE_OPTIONS.includes(
    options.pageSize as (typeof PAGE_SIZE_OPTIONS)[number],
  )
    ? (options.pageSize as (typeof PAGE_SIZE_OPTIONS)[number])
    : DEFAULT_PAGE_SIZE;
  // Capped so the offset stays a valid SQL integer - a hand-typed ?page=999999999999 would
  // otherwise make the RPC fail instead of falling back to the last page below.
  const requestedPage =
    Number.isFinite(options.page) && (options.page ?? 0) > 0
      ? Math.min(MAX_PAGE, Math.floor(options.page ?? 1))
      : 1;

  async function fetchPage(page: number): Promise<ListResult> {
    const { data, error } = await supabase.rpc("list_support_programs", {
      p_status: options.status ?? "open",
      p_it_only: Boolean(options.itOnly),
      p_investment_only: Boolean(options.investmentOnly),
      p_source: options.source ?? null,
      p_categories: parseSupportField(options.field)?.categories ?? null,
      p_term: options.q?.trim() || null,
      p_closing_days: CLOSING_SOON_DAYS,
      p_limit: pageSize,
      p_offset: (page - 1) * pageSize,
    });
    if (error) throw new Error(`Failed to load support programs: ${error.message}`);
    const result = data as ListResult | null;
    return { total: result?.total ?? 0, items: result?.items ?? [] };
  }

  let page = requestedPage;
  let result = await fetchPage(page);
  // A page past the end (an old link, or the list got shorter): show the last page and
  // report it, so the pager and the rows agree.
  if (result.items.length === 0 && result.total > 0 && page > 1) {
    page = Math.max(1, Math.ceil(result.total / pageSize));
    result = await fetchPage(page);
  }

  return { items: result.items, total: result.total, page, pageSize };
}

export async function getSupportProgram(id: string): Promise<SupportProgramDetail | null> {
  await requireUser();
  const supabase = await createClient();

  const { data, error } = await supabase
    // is_open is a PostgREST computed column (is_open(support_programs) in the migration).
    .from("support_programs")
    .select(
      "id, source, title, organization, supervising_type, category, region, recruiting, is_open, investment_linked, it_related, application_end, application_period_text, department, target, application_start, description, source_url",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load support program: ${error.message}`);
  return data;
}
