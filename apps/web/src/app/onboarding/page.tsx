import { redirect } from "next/navigation";
import { getCompany, requireUser } from "@/lib/dal";
import { OnboardingForm } from "./onboarding-form";

export default async function OnboardingPage() {
  await requireUser();
  const company = await getCompany();
  if (company) redirect("/dashboard");

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 px-4">
      <div>
        <h1 className="text-2xl font-semibold">회사 정보 입력</h1>
        <p className="text-sm text-muted-foreground">
          BizRadar를 시작하려면 회사 정보를 알려주세요.
        </p>
      </div>
      <OnboardingForm />
    </main>
  );
}
