import Link from "next/link";
import {
  DEFAULT_PAGE_SIZE,
  PAGE_SIZE_OPTIONS,
  getSupportPrograms,
} from "@/lib/supportPrograms";
import { formatDday } from "@/lib/format";
import { InvestmentBadge } from "./investment-badge";

function buildHref(page: number, q: string, investmentOnly: boolean, pageSize: number) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (investmentOnly) params.set("investment", "1");
  if (pageSize !== DEFAULT_PAGE_SIZE) params.set("pageSize", String(pageSize));
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/support?${qs}` : "/support";
}

export default async function SupportPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; investment?: string; page?: string; pageSize?: string }>;
}) {
  const params = await searchParams;
  const q = params.q ?? "";
  const investmentOnly = params.investment === "1";
  const page = params.page ? Math.max(1, parseInt(params.page, 10) || 1) : 1;
  const requestedPageSize = params.pageSize ? parseInt(params.pageSize, 10) : undefined;

  const { items, total, pageSize } = await getSupportPrograms({
    page,
    q,
    investmentOnly,
    pageSize: requestedPageSize,
  });
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">Support Radar</h1>
        <p className="shrink-0 text-sm text-muted-foreground">
          K-Startup 정부지원사업{" "}
          <span className="font-medium tabular-nums text-foreground">
            {total.toLocaleString("ko-KR")}
          </span>
          건
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <form className="flex w-full gap-2 lg:max-w-xl" action="/support">
          {investmentOnly && <input type="hidden" name="investment" value="1" />}
          {pageSize !== DEFAULT_PAGE_SIZE && (
            <input type="hidden" name="pageSize" value={pageSize} />
          )}
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="사업명 또는 주관기관 검색"
            className="w-full min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm transition-shadow focus:border-ring focus:ring-2 focus:ring-ring/30 focus:outline-none"
          />
          <button
            type="submit"
            className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium whitespace-nowrap text-primary-foreground transition-colors hover:bg-primary/85"
          >
            검색
          </button>
          {q && (
            <Link
              href={buildHref(1, "", investmentOnly, pageSize)}
              className="flex shrink-0 items-center px-2 text-sm whitespace-nowrap text-muted-foreground underline underline-offset-2"
            >
              초기화
            </Link>
          )}
        </form>

        <div className="flex gap-1">
          {(
            [
              [false, "전체"],
              [true, "투자연계형만"],
            ] as const
          ).map(([value, label]) => {
            const active = value === investmentOnly;
            return (
              <Link
                key={label}
                href={buildHref(1, q, value, pageSize)}
                aria-current={active ? "page" : undefined}
                className={
                  "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors " +
                  (active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground")
                }
              >
                {label}
              </Link>
            );
          })}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          {q ? (
            <>
              <p>&ldquo;{q}&rdquo;에 대한 검색 결과가 없습니다.</p>
              <Link
                href={buildHref(1, "", investmentOnly, pageSize)}
                className="mt-2 inline-block underline underline-offset-2"
              >
                전체 사업 보기
              </Link>
            </>
          ) : (
            <p>조건에 맞는 지원사업이 없습니다. 수집기가 매시 정각에 실행됩니다.</p>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left">
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    사업명
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    투자연계
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    주관기관
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    분류
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    지역
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide whitespace-nowrap text-muted-foreground uppercase">
                    마감
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-border last:border-0 hover:bg-muted/30"
                  >
                    <td className="max-w-sm px-4 py-3">
                      <Link
                        href={`/support/${item.id}`}
                        className="visited:text-muted-foreground hover:underline"
                      >
                        {item.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <InvestmentBadge linked={item.investment_linked} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {item.organization ?? "—"}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {item.category ?? "—"}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {item.region ?? "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums whitespace-nowrap">
                      {formatDday(item.application_end)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              <span className="text-muted-foreground">
                <span className="font-medium tabular-nums text-foreground">{page}</span> /{" "}
                <span className="tabular-nums">{totalPages}</span> 페이지
              </span>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground">페이지당</span>
                <div className="flex gap-0.5 rounded-md border border-border p-0.5">
                  {PAGE_SIZE_OPTIONS.map((size) => {
                    const active = size === pageSize;
                    return (
                      <Link
                        key={size}
                        href={buildHref(1, q, investmentOnly, size)}
                        aria-current={active ? "page" : undefined}
                        className={
                          "rounded px-2 py-1 text-xs font-medium tabular-nums transition-colors " +
                          (active
                            ? "bg-primary text-primary-foreground"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground")
                        }
                      >
                        {size}
                      </Link>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="flex gap-4">
              {page > 1 ? (
                <Link
                  href={buildHref(page - 1, q, investmentOnly, pageSize)}
                  className="underline underline-offset-2"
                >
                  이전
                </Link>
              ) : (
                <span className="text-muted-foreground/50">이전</span>
              )}
              {page < totalPages ? (
                <Link
                  href={buildHref(page + 1, q, investmentOnly, pageSize)}
                  className="underline underline-offset-2"
                >
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
