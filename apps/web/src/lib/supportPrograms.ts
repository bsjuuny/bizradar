import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

export const DEFAULT_PAGE_SIZE = 20;
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

export type SupportProgramSummary = {
  id: string;
  title: string;
  organization: string | null;
  supervising_type: string | null;
  category: string | null;
  region: string | null;
  recruiting: boolean | null;
  investment_linked: boolean;
  application_end: string | null;
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

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

export async function getSupportPrograms({
  page = 1,
  q,
  investmentOnly,
  pageSize,
}: {
  page?: number;
  q?: string;
  investmentOnly?: boolean;
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
  let query = supabase
    .from("support_programs")
    .select(
      "id, title, organization, supervising_type, category, region, recruiting, investment_linked, application_end",
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

  if (investmentOnly) {
    query = query.eq("investment_linked", true);
  }

  const term = q?.trim();
  if (term) {
    const escaped = escapeLikeTerm(term);
    query = query.or(`title.ilike.%${escaped}%,organization.ilike.%${escaped}%`);
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
      "id, title, organization, supervising_type, category, region, recruiting, investment_linked, application_end, department, target, application_start, description, source_url",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load support program: ${error.message}`);
  return data;
}
