import { requireCompany } from "@/lib/dal";

export default async function DashboardPage() {
  const { company } = await requireCompany();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">{company.name}</h1>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground">직원 규모</dt>
        <dd>{company.size_band}</dd>
        <dt className="text-muted-foreground">업종</dt>
        <dd>{company.industry ?? "-"}</dd>
        <dt className="text-muted-foreground">지역</dt>
        <dd>{company.region ?? "-"}</dd>
        <dt className="text-muted-foreground">사업 형태</dt>
        <dd>{company.business_type ?? "-"}</dd>
        <dt className="text-muted-foreground">설립연도</dt>
        <dd>{company.founded_year ?? "-"}</dd>
      </dl>
      <p className="text-sm text-muted-foreground">
        Support Radar / Market Radar는 이후 Phase에서 추가됩니다.
      </p>
    </div>
  );
}
