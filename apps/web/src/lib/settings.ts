import "server-only";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

export type Technology = { id: string; name: string };

export async function getTechnologies(): Promise<Technology[]> {
  await requireUser();
  const supabase = await createClient();
  const { data, error } = await supabase.from("technologies").select("id, name").order("name");
  if (error) throw new Error(`Failed to load technologies: ${error.message}`);
  return data ?? [];
}

export async function getCompanyTechnologyIds(companyId: string): Promise<Set<string>> {
  await requireUser();
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("company_technologies")
    .select("technology_id")
    .eq("company_id", companyId);
  if (error) throw new Error(`Failed to load company technologies: ${error.message}`);
  return new Set((data ?? []).map((row) => row.technology_id));
}
