"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type SignupActionState = { error?: string; checkEmail?: boolean } | undefined;

export async function signup(
  _prevState: SignupActionState,
  formData: FormData,
): Promise<SignupActionState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const privacyConsent = formData.get("privacy_consent") === "on";

  if (!email || !password) {
    return { error: "이메일과 비밀번호를 입력해주세요." };
  }
  if (password.length < 8) {
    return { error: "비밀번호는 8자 이상이어야 합니다." };
  }
  // Server-side, not just the form's `required` attribute - a client can submit without
  // JS/HTML validation, and consent needs to actually be enforced, not just displayed.
  if (!privacyConsent) {
    return { error: "개인정보 수집 및 이용에 동의해주세요." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    // Recorded on the auth user itself (not a separate table) so consent has a
    // verifiable timestamp per user, not just a UI checkbox nobody can prove was
    // checked - see docs/PRIVACY.md.
    options: { data: { privacy_consent_at: new Date().toISOString() } },
  });

  if (error) {
    return { error: error.message };
  }

  if (data.session) {
    // Email confirmation is disabled on this project - signed in immediately.
    redirect("/onboarding");
  }

  return { checkEmail: true };
}
