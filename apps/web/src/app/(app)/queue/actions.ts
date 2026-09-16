"use server";

import { revalidatePath } from "next/cache";
import { requireCompany } from "@/lib/dal";
import { createClient } from "@/lib/supabase/server";
import type { Category } from "@/lib/opportunities";
import { hasWatchCriteria, type QueueStatus } from "@/lib/queue";

const STATUSES = new Set<QueueStatus>(["REVIEWING", "RESPONDING", "ON_HOLD", "DECLINED"]);
const CATEGORIES = new Set<Category>(["LIKELY_IT", "NON_IT", "UNKNOWN"]);

/** Same shape as SettingsActionState: expected validation errors are returned, not
 * thrown, so the form can surface them via useActionState. Returning `undefined` on a
 * validation failure is what made a bad submit look like a successful one. */
export type WatchActionState = { error?: string; success?: boolean } | undefined;

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

export async function createWatchCondition(
  _prevState: WatchActionState,
  formData: FormData,
): Promise<WatchActionState> {
  const { company } = await requireCompany();
  const supabase = await createClient();
  const name = textValue(formData, "name");
  if (!name) return { error: "Watch 이름을 입력해주세요." };

  const rawCategory = textValue(formData, "category");
  const category: Category | null = rawCategory && CATEGORIES.has(rawCategory as Category) ? (rawCategory as Category) : null;
  const watch = {
    keyword: textValue(formData, "keyword"),
    category,
    min_budget: numberValue(formData, "minBudget"),
    max_budget: numberValue(formData, "maxBudget"),
    min_match_score: numberValue(formData, "minMatchScore"),
  };
  if (!hasWatchCriteria(watch)) {
    return {
      error: "키워드 · 카테고리 · 예산 · 최소 매칭점수 중 최소 하나는 채워주세요. 조건이 없는 Watch는 알림이 발송되지 않습니다.",
    };
  }
  if (watch.min_budget !== null && watch.max_budget !== null && watch.min_budget > watch.max_budget) {
    return { error: "최소 예산이 최대 예산보다 클 수 없습니다." };
  }

  const { error } = await supabase.from("watch_conditions").insert({
    company_id: company.id,
    name,
    keyword: watch.keyword,
    category: watch.category,
    min_budget: watch.min_budget,
    max_budget: watch.max_budget,
    min_match_score: watch.min_match_score,
    active: true,
  });
  if (error) return { error: `Watch 조건 저장에 실패했습니다: ${error.message}` };

  revalidatePath("/queue");
  return { success: true };
}

/** Pause/resume an existing watch. Until this existed the UI could only create and
 * delete, so a watch switched off outside the app (e.g. in Supabase) could never be
 * turned back on - and the digest job silently skipped every run. */
export async function toggleWatchCondition(formData: FormData) {
  const { company } = await requireCompany();
  const supabase = await createClient();
  const id = textValue(formData, "id");
  if (!id) return;

  const { error } = await supabase
    .from("watch_conditions")
    .update({ active: formData.get("nextActive") === "true" })
    .eq("company_id", company.id)
    .eq("id", id);
  if (error) throw new Error(`Failed to toggle watch condition: ${error.message}`);

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
