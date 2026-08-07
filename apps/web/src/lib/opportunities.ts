import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

export const PAGE_SIZE = 20;

export type OpportunitySummary = {
  id: string;
  title: string;
  organization: string | null;
  budget_amount: number | null;
  posted_at: string | null;
  bid_close_at: string | null;
};

export type OpportunityDetail = OpportunitySummary & {
  demand_organization: string | null;
  estimated_price: number | null;
  region_restriction: string | null;
  open_at: string | null;
  source_url: string | null;
};

export type OpportunityPage = {
  items: OpportunitySummary[];
  total: number;
  page: number;
  pageSize: number;
};

function escapeLikeTerm(term: string): string {
  return term.replace(/[%_]/g, "\\$&");
}

export async function getOpportunities({
  page = 1,
  q,
}: {
  page?: number;
  q?: string;
} = {}): Promise<OpportunityPage> {
  await requireUser();
  const supabase = await createClient();

  const safePage = Number.isFinite(page) && page > 0 ? Math.floor(page) : 1;
  const from = (safePage - 1) * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;

  let query = supabase
    .from("opportunities")
    .select("id, title, organization, budget_amount, posted_at, bid_close_at", {
      count: "exact",
    })
    .order("posted_at", { ascending: false, nullsFirst: false })
    .range(from, to);

  const term = q?.trim();
  if (term) {
    const escaped = escapeLikeTerm(term);
    query = query.or(`title.ilike.%${escaped}%,organization.ilike.%${escaped}%`);
  }

  const { data, error, count } = await query;
  if (error) throw new Error(`Failed to load opportunities: ${error.message}`);

  return { items: data ?? [], total: count ?? 0, page: safePage, pageSize: PAGE_SIZE };
}

export async function getOpportunity(id: string): Promise<OpportunityDetail | null> {
  await requireUser();
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("opportunities")
    .select(
      "id, title, organization, demand_organization, budget_amount, estimated_price, region_restriction, posted_at, bid_close_at, open_at, source_url",
    )
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`Failed to load opportunity: ${error.message}`);
  return data;
}
