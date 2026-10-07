import Link from "next/link";
import type { ReactNode } from "react";
import {
  DEFAULT_PAGE_SIZE,
  PAGE_SIZE_OPTIONS,
  getSupportPrograms,
} from "@/lib/supportPrograms";
import {
  DEFAULT_SUPPORT_STATUS,
  SUPPORT_FIELDS,
  SUPPORT_SOURCES,
  SUPPORT_STATUSES,
  SUPPORT_STATUS_LABELS,
  type SupportFieldKey,
  type SupportSource,
  type SupportStatus,
  formatSupportDeadline,
  parseSupportField,
  parseSupportSource,
  parseSupportStatus,
  supportSourceLabel,
} from "@/lib/support-display";
import { type SearchParams, one } from "@/lib/search-params";
import { InvestmentBadge } from "./investment-badge";

type ListState = {
  page: number;
  q: string;
  status: SupportStatus;
  itOnly: boolean;
  investmentOnly: boolean;
  source: SupportSource | undefined;
  field: SupportFieldKey | undefined;
  pageSize: number;
};

const HEADLINES: Record<SupportStatus, string> = {
  open: "모집 중인 지원사업",
  closing: "곧 마감되는 지원사업",
  all: "마감 포함 전체 지원사업",
};

function buildHref(state: ListState) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.status !== DEFAULT_SUPPORT_STATUS) params.set("status", state.status);
  if (state.itOnly) params.set("it", "1");
  if (state.investmentOnly) params.set("investment", "1");
  if (state.source) params.set("source", state.source);
  if (state.field) params.set("field", state.field);
  if (state.pageSize !== DEFAULT_PAGE_SIZE) params.set("pageSize", String(state.pageSize));
  if (state.page > 1) params.set("page", String(state.page));
  const qs = params.toString();
  return qs ? `/support?${qs}` : "/support";
}

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={
        "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors " +
        (active
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground")
      }
    >
      {children}
    </Link>
  );
}

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="mr-1 shrink-0 text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

export default async function SupportPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  // one(): a repeated key (?q=a&q=b) arrives as an array; only the first value counts.
  const params = await searchParams;
  const q = one(params.q);
  const status = parseSupportStatus(one(params.status));
  const itOnly = one(params.it) === "1";
  const investmentOnly = one(params.investment) === "1";
  const source = parseSupportSource(one(params.source));
  const field = parseSupportField(one(params.field))?.key;
  const page = Math.max(1, parseInt(one(params.page), 10) || 1);
  const requestedPageSize = parseInt(one(params.pageSize), 10) || undefined;

  const { items, total, pageSize } = await getSupportPrograms({
    page,
    q,
    status,
    itOnly,
    investmentOnly,
    source,
    field,
    pageSize: requestedPageSize,
  });
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const base: Omit<ListState, "page"> = {
    q,
    status,
    itOnly,
    investmentOnly,
    source,
    field,
    pageSize,
  };
  const hasFilters =
    Boolean(q) ||
    status !== DEFAULT_SUPPORT_STATUS ||
    itOnly ||
    investmentOnly ||
    Boolean(source) ||
    Boolean(field);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">Support Radar</h1>
        <p className="shrink-0 text-sm text-muted-foreground">
          {HEADLINES[status]}{" "}
          <span className="font-medium tabular-nums text-foreground">
            {total.toLocaleString("ko-KR")}
          </span>
          건
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
        <form className="flex w-full gap-2 lg:max-w-xl" action="/support">
          {status !== DEFAULT_SUPPORT_STATUS && (
            <input type="hidden" name="status" value={status} />
          )}
          {itOnly && <input type="hidden" name="it" value="1" />}
          {investmentOnly && <input type="hidden" name="investment" value="1" />}
          {source && <input type="hidden" name="source" value={source} />}
          {field && <input type="hidden" name="field" value={field} />}
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
              href={buildHref({ ...base, page: 1, q: "" })}
              className="flex shrink-0 items-center px-2 text-sm whitespace-nowrap text-muted-foreground underline underline-offset-2"
            >
              초기화
            </Link>
          )}
        </form>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <FilterGroup label="상태">
            {SUPPORT_STATUSES.map((value) => (
              <FilterLink
                key={value}
                href={buildHref({ ...base, page: 1, status: value })}
                active={value === status}
              >
                {SUPPORT_STATUS_LABELS[value]}
              </FilterLink>
            ))}
          </FilterGroup>

          <FilterGroup label="출처">
            {([undefined, ...SUPPORT_SOURCES] as const).map((value) => (
              <FilterLink
                key={value ?? "all"}
                href={buildHref({ ...base, page: 1, source: value })}
                active={value === source}
              >
                {value ? supportSourceLabel(value) : "전체"}
              </FilterLink>
            ))}
          </FilterGroup>

          <FilterGroup label="유형">
            <FilterLink
              href={buildHref({ ...base, page: 1, itOnly: !itOnly })}
              active={itOnly}
            >
              IT 관련만
            </FilterLink>
            <FilterLink
              href={buildHref({ ...base, page: 1, investmentOnly: !investmentOnly })}
              active={investmentOnly}
            >
              투자연계형만
            </FilterLink>
          </FilterGroup>
        </div>

        <FilterGroup label="지원분야">
          <FilterLink href={buildHref({ ...base, page: 1, field: undefined })} active={!field}>
            전체
          </FilterLink>
          {SUPPORT_FIELDS.map((group) => (
            <FilterLink
              key={group.key}
              href={buildHref({ ...base, page: 1, field: group.key })}
              active={group.key === field}
            >
              {group.label}
            </FilterLink>
          ))}
        </FilterGroup>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          {hasFilters ? (
            <>
              <p>
                {q ? <>&ldquo;{q}&rdquo;에 대한 </> : null}조건에 맞는 지원사업이 없습니다.
              </p>
              <Link href="/support" className="mt-2 inline-block underline underline-offset-2">
                필터 초기화
              </Link>
            </>
          ) : (
            <p>모집 중인 지원사업이 없습니다. 수집기가 1시간마다 새 공고를 가져옵니다.</p>
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
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {supportSourceLabel(item.source)}
                        {item.it_related && " · IT"}
                      </span>
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
                    {/* Wraps: besides a short D-day this can be 기업마당's free-form
                        신청기간 text, which may be long. */}
                    <td className="max-w-44 px-4 py-3 tabular-nums break-keep">
                      {formatSupportDeadline(
                        item.application_end,
                        item.application_period_text,
                        item.recruiting,
                      )}
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
