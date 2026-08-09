"use server";

import { revalidatePath } from "next/cache";
import { requireAdmin } from "@/lib/dal";
import { createAdminClient } from "@/lib/supabase/admin";

// Errors intentionally throw (caught by the root error.tsx) instead of returning a
// state object - this is a plain <form action={fn.bind(null, id)}> per row, not a
// useActionState form, so there's no inline error UI to feed. Acceptable for a small,
// operator-only admin tool; revisit if this ever needs a nicer in-page error message.
async function setApprovalStatus(
  companyId: string,
  status: "APPROVED" | "REJECTED" | "PENDING",
): Promise<void> {
  await requireAdmin();

  if (!companyId) throw new Error("잘못된 요청입니다.");

  const admin = createAdminClient();
  const { error } = await admin
    .from("companies")
    .update({ approval_status: status })
    .eq("id", companyId);

  if (error) throw new Error(`처리에 실패했습니다: ${error.message}`);

  revalidatePath("/admin");
}

export async function approveCompany(companyId: string): Promise<void> {
  await setApprovalStatus(companyId, "APPROVED");
}

export async function rejectCompany(companyId: string): Promise<void> {
  await setApprovalStatus(companyId, "REJECTED");
}

export async function revokeApproval(companyId: string): Promise<void> {
  await setApprovalStatus(companyId, "PENDING");
}
