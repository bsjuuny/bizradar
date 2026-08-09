"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/dal";

export type OnboardingActionState = { error?: string } | undefined;

const SIZE_BANDS = ["1-5", "6-10", "11-20", "21-50", "51+"] as const;

export async function createCompany(
  _prevState: OnboardingActionState,
  formData: FormData,
): Promise<OnboardingActionState> {
  const user = await requireUser();

  const name = String(formData.get("name") ?? "").trim();
  const sizeBand = String(formData.get("size_band") ?? "");
  const industry = String(formData.get("industry") ?? "").trim() || null;
  const region = String(formData.get("region") ?? "").trim() || null;
  const businessType = String(formData.get("business_type") ?? "").trim() || null;
  const foundedYearRaw = String(formData.get("founded_year") ?? "").trim();
  const foundedYear = foundedYearRaw ? Number(foundedYearRaw) : null;

  if (!name) return { error: "회사명을 입력해주세요." };
  if (!SIZE_BANDS.includes(sizeBand as (typeof SIZE_BANDS)[number])) {
    return { error: "직원 규모를 선택해주세요." };
  }
  if (
    foundedYear !== null &&
    (!Number.isInteger(foundedYear) || foundedYear < 1900 || foundedYear > 2100)
  ) {
    return { error: "설립연도를 올바르게 입력해주세요." };
  }

  const supabase = await createClient();

  // Client generates the id and this insert skips return=representation:
  // INSERT...RETURNING implicitly re-checks the table's SELECT policy, and this
  // company has no company_members row yet, so auth_company_id() is still null.
  // See docs/TROUBLESHOOTING.md.
  const companyId = crypto.randomUUID();

  const { error: companyError } = await supabase.from("companies").insert({
    id: companyId,
    name,
    size_band: sizeBand,
    industry,
    region,
    business_type: businessType,
    founded_year: foundedYear,
    // New companies start PENDING and are gated to /dashboard + /settings
    // (apps/web/src/proxy.ts) until a BizRadar operator approves them - see
    // docs/PRIVACY.md and the approval_status migration. The column default is
    // 'APPROVED' (so pre-existing companies aren't retroactively locked out); PENDING
    // only applies to companies created from here on.
    approval_status: "PENDING",
  });

  if (companyError) {
    return { error: `회사 생성에 실패했습니다: ${companyError.message}` };
  }

  const { error: memberError } = await supabase.from("company_members").insert({
    user_id: user.id,
    company_id: companyId,
    role: "owner",
  });

  if (memberError) {
    return { error: `회사 연결에 실패했습니다: ${memberError.message}` };
  }

  redirect("/dashboard");
}
