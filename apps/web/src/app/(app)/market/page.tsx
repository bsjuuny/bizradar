import { requireAdmin } from "@/lib/dal";
import { getMarketStats } from "@/lib/market";
import { StatBar } from "./stat-bar";

export default async function MarketPage() {
  // Operator-only page - see apps/web/src/lib/features.ts:isPlatformAdmin. Gates the
  // page itself, not just the nav link, so a direct URL hit is also redirected.
  await requireAdmin();
  const stats = await getMarketStats();
  const total = stats.totalItOpportunities;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">시장 통계</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          IT 관련으로 분류된 공고{" "}
          <span className="font-medium tabular-nums text-foreground">
            {total.toLocaleString("ko-KR")}
          </span>
          건 기준 입찰자격 · 투찰제한 통계
        </p>
      </div>

      {total === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          <p>아직 IT 관련으로 분류된 공고가 없습니다.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-semibold">업종제한 여부</h2>
              <p className="text-xs text-muted-foreground">
                특정 업종 등록/면허가 있어야 입찰 가능한 공고 비율
              </p>
              <div className="flex flex-col gap-3">
                <StatBar
                  label="제한 있음"
                  count={stats.industryLimited.yes}
                  total={total}
                  tone="amber"
                />
                <StatBar
                  label="제한 없음"
                  count={stats.industryLimited.no}
                  total={total}
                  tone="emerald"
                />
                {stats.industryLimited.unknown > 0 && (
                  <StatBar
                    label="공고에 명시 안 됨"
                    count={stats.industryLimited.unknown}
                    total={total}
                  />
                )}
              </div>
            </section>

            <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-semibold">참가제한 여부</h2>
              <p className="text-xs text-muted-foreground">
                실적·자격 등으로 입찰 참가 자체가 제한되는 공고 비율
              </p>
              <div className="flex flex-col gap-3">
                <StatBar
                  label="제한 있음"
                  count={stats.participationLimited.yes}
                  total={total}
                  tone="amber"
                />
                <StatBar
                  label="제한 없음"
                  count={stats.participationLimited.no}
                  total={total}
                  tone="emerald"
                />
                {stats.participationLimited.unknown > 0 && (
                  <StatBar
                    label="공고에 명시 안 됨"
                    count={stats.participationLimited.unknown}
                    total={total}
                  />
                )}
              </div>
            </section>

            <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-semibold">지역제한 여부</h2>
              <p className="text-xs text-muted-foreground">
                특정 지역 소재 업체만 입찰 가능한 공고 비율
              </p>
              <div className="flex flex-col gap-3">
                <StatBar
                  label="제한 있음"
                  count={stats.regionRestricted.restricted}
                  total={total}
                  tone="amber"
                />
                <StatBar
                  label="제한 없음"
                  count={stats.regionRestricted.unrestricted}
                  total={total}
                  tone="emerald"
                />
              </div>
              {stats.topRegionRestrictions.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5 border-t border-border pt-3">
                  {stats.topRegionRestrictions.map((r) => (
                    <span
                      key={r.name}
                      className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs"
                    >
                      {r.name}
                      <span className="text-muted-foreground tabular-nums">{r.count}</span>
                    </span>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
            <h2 className="text-sm font-semibold">조달 분류 상위 항목</h2>
            <p className="text-xs text-muted-foreground">
              어떤 종류의 IT 용역이 가장 많이 발주되는지 (나라장터 조달분류명 기준)
            </p>
            <div className="flex flex-col gap-3">
              {stats.topProcurementCategories.map((c) => (
                <StatBar key={c.name} label={c.name} count={c.count} total={total} tone="primary" />
              ))}
            </div>
          </section>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-semibold">자주 요구되는 자격/인증</h2>
              <p className="text-xs text-muted-foreground">
                AI 분석이 완료된{" "}
                <span className="tabular-nums">{stats.analyzedCount.toLocaleString("ko-KR")}</span>
                건 중 공고문에서 추출된 필수 자격/인증
              </p>
              {stats.topRequiredQualifications.length > 0 ? (
                <div className="flex flex-col gap-3">
                  {stats.topRequiredQualifications.map((q) => (
                    <StatBar
                      key={q.name}
                      label={q.name}
                      count={q.count}
                      total={stats.analyzedCount}
                      tone="primary"
                    />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  아직 자격/인증이 추출된 공고가 없습니다.
                </p>
              )}
            </section>

            <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
              <h2 className="text-sm font-semibold">요구 경력 분포</h2>
              <p className="text-xs text-muted-foreground">
                AI 분석이 완료된{" "}
                <span className="tabular-nums">{stats.analyzedCount.toLocaleString("ko-KR")}</span>
                건 중 공고문에 명시된 최소 요구 경력
              </p>
              {stats.experienceYearsDistribution.length > 0 ? (
                <div className="flex flex-col gap-3">
                  {stats.experienceYearsDistribution.map((e) => (
                    <StatBar
                      key={e.name}
                      label={e.name}
                      count={e.count}
                      total={stats.analyzedCount}
                      tone="primary"
                    />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">아직 분석된 공고가 없습니다.</p>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
