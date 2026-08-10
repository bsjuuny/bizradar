import Link from "next/link";
import {
  type Category,
  DEFAULT_PAGE_SIZE,
  DEFAULT_SORT_DIR,
  DEFAULT_SORT_FIELD,
  PAGE_SIZE_OPTIONS,
  type SortField,
  getOpportunities,
} from "@/lib/opportunities";
import { formatCurrencyKRW, formatDate } from "@/lib/format";
import { CategoryBadge } from "./category-badge";
import { MatchScoreBadge } from "./match-score-badge";

const CATEGORY_TABS: { value: Category | ""; label: string }[] = [
  { value: "", label: "전체" },
  { value: "LIKELY_IT", label: "IT 관련" },
  { value: "NON_IT", label: "IT 무관" },
  { value: "UNKNOWN", label: "미분류" },
];

const SORT_LABELS: Record<SortField, string> = {
  title: "공고명",
  organization: "발주기관",
  posted_at: "게시일",
  budget_amount: "배정예산",
};

type ListState = {
  page: number;
  q: string;
  category: string;
  pageSize: number;
  sort: SortField;
  dir: "asc" | "desc";
};

function buildQueryString(state: ListState) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.category) params.set("category", state.category);
  if (state.pageSize !== DEFAULT_PAGE_SIZE) params.set("pageSize", String(state.pageSize));
  if (state.sort !== DEFAULT_SORT_FIELD) params.set("sort", state.sort);
  if (state.dir !== DEFAULT_SORT_DIR) params.set("dir", state.dir);
  if (state.page > 1) params.set("page", String(state.page));
  return params.toString();
}

function buildHref(state: ListState) {
  const qs = buildQueryString(state);
  return qs ? `/opportunities?${qs}` : "/opportunities";
}

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    page?: string;
    category?: string;
    pageSize?: string;
    sort?: string;
    dir?: string;
  }>;
}) {
  const params = await searchParams;
  const q = params.q ?? "";
  const page = params.page ? Math.max(1, parseInt(params.page, 10) || 1) : 1;
  const category = (params.category ?? "") as Category | "";
  const requestedPageSize = params.pageSize ? parseInt(params.pageSize, 10) : undefined;

  const {
    items,
    total,
    pageSize,
    sort,
    dir,
  } = await getOpportunities({
    page,
    q,
    category: category || undefined,
    pageSize: requestedPageSize,
    sort: params.sort,
    dir: params.dir,
  });
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const base: Omit<ListState, "page"> = { q, category, pageSize, sort, dir };
  // Carried on each row's link so the detail page's "back to list" link can restore
  // this exact search/filter/sort/page state - a plain `/opportunities` back-link would
  // otherwise silently reset it, which is different from (and easy to miss compared to)
  // the browser Back button, which already preserves it via history.
  const currentListQuery = buildQueryString({ ...base, page });

  // Text columns default to ascending on first click (가나다 order reads naturally
  // top-down); date/amount columns default to descending (newest/largest first is what
  // someone browsing bid opportunities usually wants). Either way, clicking the same
  // column again just flips it.
  const TEXT_SORT_FIELDS: SortField[] = ["title", "organization"];
  function sortHref(field: SortField) {
    if (sort === field) {
      const nextDir: "asc" | "desc" = dir === "desc" ? "asc" : "desc";
      return buildHref({ ...base, page: 1, sort: field, dir: nextDir });
    }
    const firstClickDir: "asc" | "desc" = TEXT_SORT_FIELDS.includes(field) ? "asc" : "desc";
    return buildHref({ ...base, page: 1, sort: field, dir: firstClickDir });
  }

  function sortIndicator(field: SortField) {
    if (sort !== field) return null;
    return <span className="ml-1 text-[10px]">{dir === "asc" ? "▲" : "▼"}</span>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">Project Radar</h1>
        <p className="shrink-0 text-sm text-muted-foreground">
          나라장터 공공 용역 입찰공고{" "}
          <span className="font-medium tabular-nums text-foreground">
            {total.toLocaleString("ko-KR")}
          </span>
          건
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <form className="flex w-full gap-2 lg:max-w-xl" action="/opportunities">
          {category && <input type="hidden" name="category" value={category} />}
          {pageSize !== DEFAULT_PAGE_SIZE && (
            <input type="hidden" name="pageSize" value={pageSize} />
          )}
          {sort !== DEFAULT_SORT_FIELD && <input type="hidden" name="sort" value={sort} />}
          {dir !== DEFAULT_SORT_DIR && <input type="hidden" name="dir" value={dir} />}
          <input
            type="search"
            name="q"
            defaultValue={q}
            placeholder="공고명 또는 발주기관 검색"
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

        <div className="flex gap-1 overflow-x-auto pb-1 lg:pb-0">
          {CATEGORY_TABS.map((tab) => {
            const active = tab.value === category;
            return (
              <Link
                key={tab.value || "all"}
                href={buildHref({ ...base, page: 1, category: tab.value })}
                aria-current={active ? "page" : undefined}
                className={
                  "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors " +
                  (active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground")
                }
              >
                {tab.label}
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
                href={buildHref({ ...base, page: 1, q: "" })}
                className="mt-2 inline-block underline underline-offset-2"
              >
                전체 공고 보기
              </Link>
            </>
          ) : (
            <p>조건에 맞는 공고가 없습니다. 수집기가 매시 정각에 실행됩니다.</p>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
            <table className="w-full min-w-[920px] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left">
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("title")}
                      className="inline-flex items-center hover:text-foreground"
                    >
                      {SORT_LABELS.title}
                      {sortIndicator("title")}
                    </Link>
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    분류
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide whitespace-nowrap text-muted-foreground uppercase">
                    매칭
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("organization")}
                      className="inline-flex items-center hover:text-foreground"
                    >
                      {SORT_LABELS.organization}
                      {sortIndicator("organization")}
                    </Link>
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("budget_amount")}
                      className="inline-flex items-center justify-end hover:text-foreground"
                    >
                      {SORT_LABELS.budget_amount}
                      {sortIndicator("budget_amount")}
                    </Link>
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    <Link
                      href={sortHref("posted_at")}
                      className="inline-flex items-center hover:text-foreground"
                    >
                      {SORT_LABELS.posted_at}
                      {sortIndicator("posted_at")}
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
                      <Link
                        href={
                          currentListQuery
                            ? `/opportunities/${item.id}?from=${encodeURIComponent(currentListQuery)}`
                            : `/opportunities/${item.id}`
                        }
                        className="visited:text-muted-foreground hover:underline"
                      >
                        {item.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <CategoryBadge category={item.category} />
                    </td>
                    <td className="px-4 py-3">
                      <MatchScoreBadge score={item.matchScore} />
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
