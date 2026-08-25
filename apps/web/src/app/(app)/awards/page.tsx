import Link from "next/link";
import { requireAdmin } from "@/lib/dal";
import {
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT_DIR,
  DEFAULT_SORT_FIELD,
  PAGE_SIZE_OPTIONS,
  type SortField,
  getAwardResults,
} from "@/lib/awards";
import { formatCurrencyKRW, formatDate, formatDateTime } from "@/lib/format";

const SORT_LABELS: Record<SortField, string> = {
  awarded_at: "낙찰일",
  award_amount: "낙찰금액",
  award_rate: "낙찰률",
  participant_count: "참가업체 수",
};

type ListState = {
  page: number;
  q: string;
  pageSize: number;
  sort: SortField;
  dir: "asc" | "desc";
};

function buildQueryString(state: ListState) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.pageSize !== DEFAULT_PAGE_SIZE) params.set("pageSize", String(state.pageSize));
  if (state.sort !== DEFAULT_SORT_FIELD) params.set("sort", state.sort);
  if (state.dir !== DEFAULT_SORT_DIR) params.set("dir", state.dir);
  if (state.page > 1) params.set("page", String(state.page));
  return params.toString();
}

function buildHref(state: ListState) {
  const qs = buildQueryString(state);
  return qs ? `/awards?${qs}` : "/awards";
}

export default async function AwardsPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    page?: string;
    pageSize?: string;
    sort?: string;
    dir?: string;
  }>;
}) {
  // Operator-only page, same as /market - see apps/web/src/lib/features.ts:
  // isPlatformAdmin. Gates the page itself, not just the nav link, so a direct URL
  // hit is also redirected.
  await requireAdmin();

  const params = await searchParams;
  const q = params.q ?? "";
  const page = params.page ? Math.max(1, parseInt(params.page, 10) || 1) : 1;
  const requestedPageSize = params.pageSize ? parseInt(params.pageSize, 10) : undefined;

  const { items, total, pageSize, sort, dir } = await getAwardResults({
    page,
    q,
    pageSize: requestedPageSize,
    sort: params.sort,
    dir: params.dir,
  });
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const base: Omit<ListState, "page"> = { q, pageSize, sort, dir };

  function sortHref(field: SortField) {
    if (sort === field) {
      const nextDir: "asc" | "desc" = dir === "desc" ? "asc" : "desc";
      return buildHref({ ...base, page: 1, sort: field, dir: nextDir });
    }
    return buildHref({ ...base, page: 1, sort: field, dir: "desc" });
  }

  function sortIndicator(field: SortField) {
    if (sort !== field) return null;
    return <span className="ml-1 text-[10px]">{dir === "asc" ? "▲" : "▼"}</span>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">낙찰 결과</h1>
        <p className="shrink-0 text-sm text-muted-foreground">
          나라장터 개찰 결과{" "}
          <span className="font-medium tabular-nums text-foreground">
            {total.toLocaleString("ko-KR")}
          </span>
          건
        </p>
      </div>

      <form className="flex w-full gap-2 lg:max-w-xl" action="/awards">
        {pageSize !== DEFAULT_PAGE_SIZE && <input type="hidden" name="pageSize" value={pageSize} />}
        {sort !== DEFAULT_SORT_FIELD && <input type="hidden" name="sort" value={sort} />}
        {dir !== DEFAULT_SORT_DIR && <input type="hidden" name="dir" value={dir} />}
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="공고명 또는 낙찰업체 검색"
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
            href={buildHref({ ...base, page: 1, q: "" })}
            className="flex shrink-0 items-center px-2 text-sm whitespace-nowrap text-muted-foreground underline underline-offset-2"
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
              <Link
                href={buildHref({ ...base, page: 1, q: "" })}
                className="mt-2 inline-block underline underline-offset-2"
              >
                전체 결과 보기
              </Link>
            </>
          ) : (
            <p>아직 수집된 낙찰 결과가 없습니다.</p>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
            <table className="w-full min-w-[960px] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left">
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    공고명
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    낙찰업체
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("award_amount")}
                      className="inline-flex items-center justify-end hover:text-foreground"
                    >
                      {SORT_LABELS.award_amount}
                      {sortIndicator("award_amount")}
                    </Link>
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("award_rate")}
                      className="inline-flex items-center justify-end hover:text-foreground"
                    >
                      {SORT_LABELS.award_rate}
                      {sortIndicator("award_rate")}
                    </Link>
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("participant_count")}
                      className="inline-flex items-center justify-end hover:text-foreground"
                    >
                      {SORT_LABELS.participant_count}
                      {sortIndicator("participant_count")}
                    </Link>
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    개찰일시
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("awarded_at")}
                      className="inline-flex items-center hover:text-foreground"
                    >
                      {SORT_LABELS.awarded_at}
                      {sortIndicator("awarded_at")}
                    </Link>
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
                      {item.opportunityId ? (
                        <Link
                          href={`/opportunities/${item.opportunityId}`}
                          className="visited:text-muted-foreground hover:underline"
                        >
                          {item.title ?? "(제목 없음)"}
                        </Link>
                      ) : (
                        (item.title ?? "(제목 없음)")
                      )}
                    </td>
                    <td className="px-4 py-3">{item.winner_name}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                      {formatCurrencyKRW(item.award_amount)}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                      {item.award_rate === null
                        ? "—"
                        : `${item.award_rate.toLocaleString("ko-KR", { maximumFractionDigits: 4 })}%`}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                      {item.participant_count === null
                        ? "—"
                        : `${item.participant_count.toLocaleString("ko-KR")}개사`}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {formatDateTime(item.opened_at)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {formatDate(item.awarded_at)}
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
                        href={buildHref({ ...base, page: 1, pageSize: size })}
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
                  href={buildHref({ ...base, page: page - 1 })}
                  className="underline underline-offset-2"
                >
                  이전
                </Link>
              ) : (
                <span className="text-muted-foreground/50">이전</span>
              )}
              {page < totalPages ? (
                <Link
                  href={buildHref({ ...base, page: page + 1 })}
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
