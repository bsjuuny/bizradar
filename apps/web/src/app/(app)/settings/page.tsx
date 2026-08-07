import { requireCompany } from "@/lib/dal";
import { getCompanyTechnologyIds, getTechnologies } from "@/lib/settings";
import { SettingsForm } from "./settings-form";

export default async function SettingsPage() {
  const { company, company_id: companyId } = await requireCompany();
  const [technologies, selectedTechnologyIds] = await Promise.all([
    getTechnologies(),
    getCompanyTechnologyIds(companyId),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">회사 설정</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          회사 프로필과 Company Match 매칭 조건을 관리합니다.
        </p>
      </div>
      <SettingsForm
        company={company}
        technologies={technologies}
        selectedTechnologyIds={selectedTechnologyIds}
      />
    </div>
  );
}
