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

  if (!email || !password) {
    return { error: "이메일과 비밀번호를 입력해주세요." };
  }
  if (password.length < 8) {
    return { error: "비밀번호는 8자 이상이어야 합니다." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({ email, password });

  if (error) {
    return { error: error.message };
  }

  if (data.session) {
    // Email confirmation is disabled on this project - signed in immediately.
    redirect("/onboarding");
  }

  return { checkEmail: true };
}
