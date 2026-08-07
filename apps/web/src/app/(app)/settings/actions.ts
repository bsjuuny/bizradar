"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { requireCompany } from "@/lib/dal";

export type SettingsActionState = { error?: string; success?: boolean } | undefined;

const SIZE_BANDS = ["1-5", "6-10", "11-20", "21-50", "51+"] as const;

function parseNumberOrNull(value: FormDataEntryValue | null): number | null {
  const trimmed = String(value ?? "").trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function updateSettings(
  _prevState: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const { company_id: companyId } = await requireCompany();

  const name = String(formData.get("name") ?? "").trim();
  const sizeBand = String(formData.get("size_band") ?? "");
  const industry = String(formData.get("industry") ?? "").trim() || null;
  const region = String(formData.get("region") ?? "").trim() || null;
  const businessType = String(formData.get("business_type") ?? "").trim() || null;
  const foundedYear = parseNumberOrNull(formData.get("founded_year"));
  const budgetMin = parseNumberOrNull(formData.get("budget_min"));
  const budgetMax = parseNumberOrNull(formData.get("budget_max"));
  const experienceYears = parseNumberOrNull(formData.get("experience_years")) ?? 0;
  const qualifications = String(formData.get("qualifications") ?? "")
    .split(",")
    .map((q) => q.trim())
    .filter(Boolean);
  const technologyIds = formData.getAll("technology_ids").map(String);

  if (!name) return { error: "회사명을 입력해주세요." };
  if (!SIZE_BANDS.includes(sizeBand as (typeof SIZE_BANDS)[number])) {
    return { error: "직원 규모를 선택해주세요." };
  }
  if (budgetMin !== null && budgetMax !== null && budgetMin > budgetMax) {
    return { error: "최소 예산이 최대 예산보다 클 수 없습니다." };
  }
  if (experienceYears < 0) {
    return { error: "경력 연수는 0 이상이어야 합니다." };
  }

  const supabase = await createClient();

  const { error: companyError } = await supabase
    .from("companies")
    .update({
      name,
      size_band: sizeBand,
      industry,
      region,
      business_type: businessType,
      founded_year: foundedYear,
      budget_min: budgetMin,
      budget_max: budgetMax,
      experience_years: experienceYears,
      qualifications,
    })
    .eq("id", companyId);

  if (companyError) {
    return { error: `저장에 실패했습니다: ${companyError.message}` };
  }

  // Replace the tech stack wholesale - simplest correct approach at this scale
  // (a handful of rows per company, not worth a diff/patch).
  const { error: deleteError } = await supabase
    .from("company_technologies")
    .delete()
    .eq("company_id", companyId);
  if (deleteError) {
    return { error: `기술 스택 저장에 실패했습니다: ${deleteError.message}` };
  }

  if (technologyIds.length > 0) {
    const { error: insertError } = await supabase
      .from("company_technologies")
      .insert(
        technologyIds.map((technologyId) => ({
          company_id: companyId,
          technology_id: technologyId,
        })),
      );
    if (insertError) {
      return { error: `기술 스택 저장에 실패했습니다: ${insertError.message}` };
    }
  }

  revalidatePath("/settings");
  revalidatePath("/dashboard");
  return { success: true };
}
