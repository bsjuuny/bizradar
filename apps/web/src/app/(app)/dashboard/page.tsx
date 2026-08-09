import Link from "next/link";
import { requireCompany } from "@/lib/dal";
import { isChallengeEnabled } from "@/lib/features";

export default async function DashboardPage() {
  const { company } = await requireCompany();
  const challengeEnabled = isChallengeEnabled();
  const isPending = company.approval_status === "PENDING";
  const isRejected = company.approval_status === "REJECTED";

  return (
    <div className="flex flex-col gap-8">
      <header>
        <p className="text-sm font-medium text-muted-foreground">오늘의 비즈니스 레이더</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">{company.name}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          회사 조건에 맞는 공공 프로젝트와 공모전을 한곳에서 확인하세요.
        </p>
      </header>

      {isPending && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <p className="font-medium">회원 승인 대기 중입니다.</p>
          <p className="mt-1 text-amber-800 dark:text-amber-300">
            승인 전까지는 대시보드와 설정만 이용할 수 있습니다. 승인이 완료되면 Project
            Radar 등 나머지 기능이 열립니다.
          </p>
        </div>
      )}
      {isRejected && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <p className="font-medium">가입이 승인되지 않았습니다.</p>
          <p className="mt-1 text-muted-foreground">문의사항은 운영자에게 연락해주세요.</p>
        </div>
      )}

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-medium tracking-wide text-muted-foreground">회사 프로필</p>
              <h2 className="mt-1 text-lg font-semibold">회사 정보</h2>
            </div>
            <Link href="/settings" className="text-sm font-medium underline underline-offset-4">
              정보 수정
            </Link>
          </div>
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
            {[
              ["직원 규모", company.size_band],
              ["업종", company.industry],
              ["지역", company.region],
              ["사업 형태", company.business_type],
              ["설립연도", company.founded_year],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-muted/60 p-3">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 font-medium">{value || "미입력"}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
          {isPending ? (
            <div className="rounded-2xl border border-dashed border-border p-5 text-sm text-muted-foreground">
              승인 후 Project Radar · Support Radar{challengeEnabled ? " · CHALLENGE" : ""} 메뉴가 열립니다.
            </div>
          ) : (
            <>
              <Link href="/opportunities" className="group rounded-2xl border border-border bg-card p-5 transition hover:-translate-y-0.5 hover:shadow-sm">
                <p className="text-xs font-medium text-muted-foreground">PROJECT RADAR</p>
                <h2 className="mt-2 text-lg font-semibold">공공 입찰 기회 찾기</h2>
                <p className="mt-1 text-sm text-muted-foreground">회사 프로필 기반 매칭 점수와 AI 분석을 확인합니다.</p>
                <span className="mt-4 inline-block text-sm font-medium group-hover:underline">바로가기 →</span>
              </Link>
              <Link href="/support" className="group rounded-2xl border border-border bg-card p-5 transition hover:-translate-y-0.5 hover:shadow-sm">
                <p className="text-xs font-medium text-muted-foreground">SUPPORT RADAR</p>
                <h2 className="mt-2 text-lg font-semibold">정부지원사업 찾기</h2>
                <p className="mt-1 text-sm text-muted-foreground">TIPS 등 투자연계형 프로그램을 포함한 K-Startup 공고를 확인합니다.</p>
                <span className="mt-4 inline-block text-sm font-medium group-hover:underline">바로가기 →</span>
              </Link>
              {challengeEnabled && (
                <Link href="/challenges" className="group rounded-2xl border border-border bg-card p-5 transition hover:-translate-y-0.5 hover:shadow-sm">
                  <p className="text-xs font-medium text-muted-foreground">CHALLENGE</p>
                  <h2 className="mt-2 text-lg font-semibold">공모전 탐색하기</h2>
                  <p className="mt-1 text-sm text-muted-foreground">참가 조건과 AI 활용 정책을 빠르게 비교합니다.</p>
                  <span className="mt-4 inline-block text-sm font-medium group-hover:underline">바로가기 →</span>
                </Link>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
