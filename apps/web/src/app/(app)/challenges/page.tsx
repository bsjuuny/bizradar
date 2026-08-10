import Link from "next/link";
import { notFound } from "next/navigation";
import {
  CHALLENGE_STATUSES,
  CHALLENGE_TYPES,
  PARTICIPATION_TYPES,
  POLICY_STATUSES,
  getChallenges,
  parseChallengeFilters,
  type ChallengeFilters,
} from "@/lib/challenges";
import { isChallengeEnabled } from "@/lib/features";
import { formatCurrencyKRW, formatDate, formatDday } from "@/lib/format";
import {
  PARTICIPATION_LABELS,
  POLICY_LABELS,
  STATUS_LABELS,
  TYPE_LABELS,
  PolicyBadge,
  StatusBadge,
  TypeBadge,
} from "./challenge-badges";

type SearchParams = Record<string, string | string[] | undefined>;

function buildHref(filters: ChallengeFilters, overrides: Partial<ChallengeFilters>) {
  const next = { ...filters, ...overrides };
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.type) params.set("type", next.type);
  if (next.status) params.set("status", next.status);
  if (next.ai) params.set("ai", next.ai);
  if (next.aiCoding) params.set("aiCoding", next.aiCoding);
  if (next.participation) params.set("participation", next.participation);
  if (next.entry) params.set("entry", next.entry);
  if (next.hasPrize) params.set("hasPrize", "true");
  if (next.organizer) params.set("organizer", next.organizer);
  if (next.technology) params.set("technology", next.technology);
  if (next.page > 1) params.set("page", String(next.page));
  const query = params.toString();
  return query ? `/challenges?${query}` : "/challenges";
}

function teamLabel(min: number | null, max: number | null) {
  if (min === 1 && max === 1) return "개인 참가";
  if (max && max > 1) return `개인/팀 · 최대 ${max}명`;
  return min === 1 ? "개인 참가 가능" : "참가 형태 미확인";
}

export default async function ChallengesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  if (!isChallengeEnabled()) notFound();
  const filters = parseChallengeFilters(await searchParams);
  const { items, total, pageSize } = await getChallenges(filters);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="text-sm font-medium text-primary">BizRadar</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">CHALLENGE</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          공모전·해커톤·경진대회의 참가 조건과 AI 활용 정책을 원문 근거와 함께 확인하세요.
        </p>
      </header>

      <div className="flex flex-wrap gap-2" aria-label="AI 정책 빠른 필터">
        {POLICY_STATUSES.map((policy) => (
          <Link
            key={policy}
            href={buildHref(filters, { ai: policy, page: 1 })}
            aria-current={filters.ai === policy ? "page" : undefined}
            className={
              "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors " +
              (filters.ai === policy
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border hover:bg-muted")
            }
          >
            {POLICY_LABELS[policy]}
          </Link>
        ))}
        {filters.ai && (
          <Link href={buildHref(filters, { ai: undefined, page: 1 })} className="px-2 py-1.5 text-xs underline">
            AI 필터 해제
          </Link>
        )}
      </div>

      <form action="/challenges" className="grid gap-3 rounded-xl border border-border p-4 md:grid-cols-4">
        <input
          type="search"
          name="q"
          defaultValue={filters.q}
          placeholder="공모전명, 기관, 기술 검색"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm md:col-span-2"
        />
        <select name="type" defaultValue={filters.type ?? ""} className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
          <option value="">모든 유형</option>
          {CHALLENGE_TYPES.map((type) => <option key={type} value={type}>{TYPE_LABELS[type]}</option>)}
        </select>
        <select name="status" defaultValue={filters.status ?? ""} className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
          <option value="">모든 진행 상태</option>
          {CHALLENGE_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
        </select>
        <select name="participation" defaultValue={filters.participation ?? ""} className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
          <option value="">온라인/오프라인 전체</option>
          {PARTICIPATION_TYPES.map((type) => <option key={type} value={type}>{PARTICIPATION_LABELS[type]}</option>)}
        </select>
        <select name="entry" defaultValue={filters.entry ?? ""} className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
          <option value="">참가 형태 전체</option>
          <option value="individual">개인 참가 가능</option>
          <option value="team">팀 참가</option>
        </select>
        <select name="aiCoding" defaultValue={filters.aiCoding ?? ""} className="rounded-lg border border-border bg-background px-3 py-2 text-sm">
          <option value="">AI Coding 정책 전체</option>
          {POLICY_STATUSES.map((policy) => <option key={policy} value={policy}>{POLICY_LABELS[policy]}</option>)}
        </select>
        <input type="text" name="organizer" defaultValue={filters.organizer ?? ""} placeholder="주최기관" className="rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        <input type="text" name="technology" defaultValue={filters.technology ?? ""} placeholder="기술 분야 (예: AI)" className="rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        <label className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
          <input type="checkbox" name="hasPrize" value="true" defaultChecked={filters.hasPrize} /> 상금 있음
        </label>
        {filters.ai && <input type="hidden" name="ai" value={filters.ai} />}
        <div className="flex gap-2 md:col-span-4">
          <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">검색·필터 적용</button>
          <Link href="/challenges" className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted">초기화</Link>
        </div>
      </form>

      <div className="flex items-center justify-between text-sm">
        <p className="text-muted-foreground">총 {total.toLocaleString("ko-KR")}건</p>
        <p className="text-muted-foreground">{filters.page} / {totalPages} 페이지</p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border py-16 text-center">
          <p className="font-medium">조건에 맞는 공모전이 없습니다.</p>
          <p className="mt-1 text-sm text-muted-foreground">검색어나 필터를 변경해 보세요.</p>
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {items.map((challenge) => (
            <article key={challenge.id} className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5 transition hover:-translate-y-0.5 hover:shadow-sm last:odd:xl:col-span-2">
              <div className="flex flex-wrap gap-2"><TypeBadge type={challenge.challenge_type} /><StatusBadge status={challenge.status} /><PolicyBadge policy={challenge.ai_policy} /></div>
              <div>
                <Link href={`/challenges/${challenge.id}`} className="text-lg font-semibold text-balance visited:text-muted-foreground hover:underline">{challenge.title}</Link>
                <p className="mt-1 text-sm text-muted-foreground">{challenge.organizer ?? "주최기관 미확인"}</p>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div><dt className="text-xs text-muted-foreground">접수 마감</dt><dd>{formatDate(challenge.apply_end_date)} · <strong>{formatDday(challenge.apply_end_date)}</strong></dd></div>
                <div><dt className="text-xs text-muted-foreground">상금</dt><dd>{challenge.prize ?? formatCurrencyKRW(challenge.total_prize_amount)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">참가 대상</dt><dd>{teamLabel(challenge.team_min, challenge.team_max)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">참여 방식</dt><dd>{PARTICIPATION_LABELS[challenge.participation_type]}</dd></div>
              </dl>
              {challenge.technology_keywords.length > 0 && <div className="flex flex-wrap gap-1.5">{challenge.technology_keywords.slice(0, 5).map((tag) => <span key={tag} className="rounded bg-muted px-2 py-1 text-xs">#{tag}</span>)}</div>}
            </article>
          ))}
        </div>
      )}

      <nav className="flex items-center justify-between text-sm" aria-label="페이지 이동">
        {filters.page > 1 ? <Link href={buildHref(filters, { page: filters.page - 1 })} className="underline">이전</Link> : <span className="text-muted-foreground/50">이전</span>}
        {filters.page < totalPages ? <Link href={buildHref(filters, { page: filters.page + 1 })} className="underline">다음</Link> : <span className="text-muted-foreground/50">다음</span>}
      </nav>
    </div>
  );
}
