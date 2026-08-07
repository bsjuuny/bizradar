import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const getUser = cache(async () => {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
});

export async function requireUser() {
  const user = await getUser();
  if (!user) redirect("/login");
  return user;
}

export type CompanyMembership = {
  company_id: string;
  role: string;
  company: {
    id: string;
    name: string;
    size_band: string;
    industry: string | null;
    region: string | null;
    business_type: string | null;
    founded_year: number | null;
    budget_min: number | null;
    budget_max: number | null;
    experience_years: number;
    qualifications: string[];
  };
};

const COMPANY_COLUMNS =
  "id, name, size_band, industry, region, business_type, founded_year, " +
  "budget_min, budget_max, experience_years, qualifications";

export const getCompany = cache(async (): Promise<CompanyMembership | null> => {
  const user = await getUser();
  if (!user) return null;

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("company_members")
    .select(`company_id, role, company:companies(${COMPANY_COLUMNS})`)
    .eq("user_id", user.id)
    .maybeSingle();

  // A real query error (e.g. a transient Supabase outage) must not be treated the same
  // as "this user has no company yet" - that conflation was a live-found bug: it
  // silently redirected an existing member to /onboarding during an outage instead of
  // showing an error, risking a duplicate company being created. `.maybeSingle()`
  // itself reports zero rows as `{ data: null, error: null }`, so `error` here only
  // ever means a genuine failure, never "not found".
  if (error) throw new Error(`Failed to load company: ${error.message}`);
  if (!data) return null;
  return data as unknown as CompanyMembership;
});

export async function requireCompany() {
  const company = await getCompany();
  if (!company) redirect("/onboarding");
  return company;
}
