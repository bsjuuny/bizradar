import Link from "next/link";
import { getOpportunities } from "@/lib/opportunities";
import { formatCurrencyKRW, formatDate } from "@/lib/format";

function buildHref(page: number, q: string) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/opportunities?${qs}` : "/opportunities";
}

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const params = await searchParams;
  const q = params.q ?? "";
  const page = params.page ? Math.max(1, parseInt(params.page, 10) || 1) : 1;

  const { items, total, pageSize } = await getOpportunities({ page, q });
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Project Radar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          나라장터에서 수집된 공공 용역 입찰공고 {total.toLocaleString("ko-KR")}건
        </p>
      </div>

      <form className="flex gap-2" action="/opportunities">
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="공고명 또는 발주기관 검색"
          className="w-full min-w-0 max-w-sm rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
        <button
          type="submit"
          className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium whitespace-nowrap text-primary-foreground hover:bg-primary/80"
        >
          검색
        </button>
        {q && (
          <Link
            href="/opportunities"
            className="flex shrink-0 items-center px-2 text-sm whitespace-nowrap text-muted-foreground underline"
          >
            초기화
          </Link>
        )}
      </form>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          {q ? (
            <>
              <p>&ldquo;{q}&rdquo;에 대한 검색 결과가 없습니다.</p>
              <Link href="/opportunities" className="mt-2 inline-block underline">
                전체 공고 보기
              </Link>
            </>
          ) : (
            <p>아직 수집된 공고가 없습니다. 수집기가 매시 정각에 실행됩니다.</p>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">공고명</th>
                  <th className="px-4 py-2.5 font-medium">발주기관</th>
                  <th className="px-4 py-2.5 text-right font-medium">배정예산</th>
                  <th className="px-4 py-2.5 font-medium">게시일</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                    <td className="max-w-sm px-4 py-3">
                      <Link href={`/opportunities/${item.id}`} className="hover:underline">
                        {item.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {item.organization ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                      {formatCurrencyKRW(item.budget_amount)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {formatDate(item.posted_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {page} / {totalPages} 페이지
            </span>
            <div className="flex gap-2">
              {page > 1 ? (
                <Link href={buildHref(page - 1, q)} className="underline">
                  이전
                </Link>
              ) : (
                <span className="text-muted-foreground/50">이전</span>
              )}
              {page < totalPages ? (
                <Link href={buildHref(page + 1, q)} className="underline">
                  다음
                </Link>
              ) : (
                <span className="text-muted-foreground/50">다음</span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
