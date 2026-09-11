"use server";

import { revalidatePath } from "next/cache";
import { requireCompany } from "@/lib/dal";
import { createClient } from "@/lib/supabase/server";
import type { Category } from "@/lib/opportunities";
import type { QueueStatus } from "@/lib/queue";

const STATUSES = new Set<QueueStatus>(["REVIEWING", "RESPONDING", "ON_HOLD", "DECLINED"]);
const CATEGORIES = new Set<Category>(["LIKELY_IT", "NON_IT", "UNKNOWN"]);

function textValue(formData: FormData, key: string) {
  const value = formData.get(key);
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function numberValue(formData: FormData, key: string) {
  const value = textValue(formData, key);
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function saveOpportunity(formData: FormData) {
  const { company } = await requireCompany();
  const supabase = await createClient();
  const opportunityId = textValue(formData, "opportunityId");
  if (!opportunityId) return;

  const rawStatus = textValue(formData, "status") ?? "REVIEWING";
  const status: QueueStatus = STATUSES.has(rawStatus as QueueStatus)
    ? (rawStatus as QueueStatus)
    : "REVIEWING";

  const { error } = await supabase.from("saved_opportunities").upsert(
    {
      company_id: company.id,
      opportunity_id: opportunityId,
      status,
      owner_name: textValue(formData, "ownerName"),
      note: textValue(formData, "note"),
    },
    { onConflict: "company_id,opportunity_id" },
  );
  if (error) throw new Error(`Failed to save opportunity: ${error.message}`);

  revalidatePath("/queue");
  revalidatePath("/opportunities");
}

export async function removeSavedOpportunity(formData: FormData) {
  const { company } = await requireCompany();
  const supabase = await createClient();
  const opportunityId = textValue(formData, "opportunityId");
  if (!opportunityId) return;

  const { error } = await supabase
    .from("saved_opportunities")
    .delete()
    .eq("company_id", company.id)
    .eq("opportunity_id", opportunityId);
  if (error) throw new Error(`Failed to remove saved opportunity: ${error.message}`);

  revalidatePath("/queue");
  revalidatePath("/opportunities");
}

export async function createWatchCondition(formData: FormData) {
  const { company } = await requireCompany();
  const supabase = await createClient();
  const name = textValue(formData, "name");
  if (!name) return;

  const rawCategory = textValue(formData, "category");
  const category = rawCategory && CATEGORIES.has(rawCategory as Category) ? rawCategory : null;

  const { error } = await supabase.from("watch_conditions").insert({
    company_id: company.id,
    name,
    keyword: textValue(formData, "keyword"),
    category,
    min_budget: numberValue(formData, "minBudget"),
    max_budget: numberValue(formData, "maxBudget"),
    min_match_score: numberValue(formData, "minMatchScore"),
    active: true,
  });
  if (error) throw new Error(`Failed to create watch condition: ${error.message}`);

  revalidatePath("/queue");
}

export async function deleteWatchCondition(formData: FormData) {
  const { company } = await requireCompany();
  const supabase = await createClient();
  const id = textValue(formData, "id");
  if (!id) return;

  const { error } = await supabase
    .from("watch_conditions")
    .delete()
    .eq("company_id", company.id)
    .eq("id", id);
  if (error) throw new Error(`Failed to delete watch condition: ${error.message}`);

  revalidatePath("/queue");
}
