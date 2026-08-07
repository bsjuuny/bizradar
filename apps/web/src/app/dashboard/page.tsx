import { requireCompany } from "@/lib/dal";
import { logout } from "./actions";

export default async function DashboardPage() {
  const membership = await requireCompany();
  const { company } = membership;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 px-4 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{company.name}</h1>
        <form action={logout}>
          <button type="submit" className="text-sm underline">
            로그아웃
          </button>
        </form>
      </div>
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
        Project Radar / Support Radar / Market Radar는 이후 Phase에서 추가됩니다.
      </p>
    </main>
  );
}
