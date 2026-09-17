import Link from "next/link";
import { formatCurrencyKRW, formatDateTime, formatDday } from "@/lib/format";
import {
  describeWatchCriteria,
  getTodayQueue,
  hasWatchCriteria,
  type QueueItem,
  type QueueStatus,
} from "@/lib/queue";
import { MatchScoreBadge } from "../opportunities/match-score-badge";
import { deleteWatchCondition, removeSavedOpportunity, saveOpportunity, toggleWatchCondition } from "./actions";
import { WatchForm } from "./watch-form";

const STATUS_LABELS: Record<QueueStatus, string> = {
  REVIEWING: "Reviewing",
  RESPONDING: "Responding",
  ON_HOLD: "On hold",
  DECLINED: "Declined",
};

const STATUS_OPTIONS = Object.entries(STATUS_LABELS) as [QueueStatus, string][];

function SavedForm({ item }: { item: QueueItem }) {
  return (
    <form action={saveOpportunity} className="grid gap-2 rounded-lg border border-border bg-muted/30 p-3 sm:grid-cols-[1fr_1fr_auto]">
      <input type="hidden" name="opportunityId" value={item.id} />
      <select
        name="status"
        defaultValue={item.saved?.status ?? "REVIEWING"}
        className="rounded-md border border-border bg-background px-2 py-1.5 text-xs"
      >
        {STATUS_OPTIONS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <input
        name="ownerName"
        defaultValue={item.saved?.owner_name ?? ""}
        placeholder="Owner"
        className="rounded-md border border-border bg-background px-2 py-1.5 text-xs"
      />
      <button className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground">
        Save
      </button>
      <input
        name="note"
        defaultValue={item.saved?.note ?? ""}
        placeholder="Decision note"
        className="sm:col-span-3 rounded-md border border-border bg-background px-2 py-1.5 text-xs"
      />
    </form>
  );
}

function QueueCard({ item }: { item: QueueItem }) {
  return (
    <article className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <MatchScoreBadge score={item.matchScore} />
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
              {formatDday(item.bid_close_at)}
            </span>
            {item.saved && (
              <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                {STATUS_LABELS[item.saved.status]}
              </span>
            )}
            {item.hasRevisionChange && (
              <Link
                href={`/opportunities/${item.id}`}
                className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 hover:underline dark:bg-amber-950 dark:text-amber-300"
              >
                변경공고
              </Link>
            )}
          </div>
          <h2 className="mt-3 text-lg font-semibold leading-snug">
            <Link href={`/opportunities/${item.id}`} className="hover:underline">
              {item.title}
            </Link>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {item.organization ?? "Unknown organization"} · {formatCurrencyKRW(item.budget_amount)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Deadline: {formatDateTime(item.bid_close_at)}
          </p>
          {item.watchMatches.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {item.watchMatches.map((name) => (
                <span key={name} className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200">
                  Watch: {name}
                </span>
              ))}
            </div>
          )}
        </div>
        {item.saved && (
          <form action={removeSavedOpportunity}>
            <input type="hidden" name="opportunityId" value={item.id} />
            <button className="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted">
              Remove
            </button>
          </form>
        )}
      </div>
      <div className="mt-4">
        <SavedForm item={item} />
      </div>
    </article>
  );
}

export default async function QueuePage() {
  const queue = await getTodayQueue();
  const urgentIds = new Set(queue.urgentItems.map((item) => item.id));
  const highPriority = queue.items.filter(
    (item) => !urgentIds.has(item.id) && (item.saved || item.watchMatches.length > 0 || (item.matchScore ?? 0) >= 70),
  );
  const remaining = queue.items.filter((item) => !urgentIds.has(item.id));
  // 긴급(D-3) 섹션이 이미 있으면, 그 아래 "그 외 주목할 공고"는 실제로 주목할 만한
  // 항목(highPriority)만 보여준다 - 긴급 항목이 오늘 볼 것을 이미 다뤘는데 점수 낮은
  // 나머지 20건으로 억지로 채우면 신호보다 소음이 커진다. 긴급도 없을 때만 폴백으로 채운다.
  const visibleItems =
    highPriority.length > 0 ? highPriority : queue.urgentItems.length > 0 ? [] : remaining.slice(0, 20);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="text-sm font-medium text-muted-foreground">Decision workflow</p>
        <h1 className="text-2xl font-semibold tracking-tight">Today Queue</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Review the opportunities most likely to need action today. Save a notice, assign an owner,
          set a response status, and create Watch rules for recurring searches.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-4">
        {[
          ["Urgent (D-3)", queue.urgentItems.length],
          ["Saved", queue.savedCount],
          ["Responding", queue.respondingCount],
          // 꺼져 있거나 조건이 없는 Watch는 실제로 아무것도 발송하지 않으므로 집계에서 뺀다.
          ["Watch rules (active)", queue.watchConditions.filter((watch) => watch.active && hasWatchCriteria(watch)).length],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-6">
          {queue.urgentItems.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-red-700 dark:text-red-400">
                오늘 결정 필요 (마감 D-3 이내)
              </h2>
              {queue.urgentItems.map((item) => (
                <QueueCard key={item.id} item={item} />
              ))}
            </div>
          )}

          <div className="flex flex-col gap-3">
            {queue.urgentItems.length > 0 && visibleItems.length > 0 && (
              <h2 className="text-sm font-semibold text-muted-foreground">그 외 주목할 공고</h2>
            )}
            {visibleItems.length === 0 && queue.urgentItems.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
                No opportunities are ready for the queue yet.
              </div>
            ) : (
              visibleItems.map((item) => <QueueCard key={item.id} item={item} />)
            )}
          </div>
        </div>

        <aside className="flex flex-col gap-4">
          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">New Watch Condition</h2>
            <WatchForm />
          </section>

          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">Watch Rules</h2>
            <div className="mt-3 flex flex-col gap-2">
              {queue.watchConditions.length === 0 ? (
                <p className="text-sm text-muted-foreground">No watch conditions yet.</p>
              ) : (
                queue.watchConditions.map((watch) => {
                  // 조건이 하나도 없는 Watch는 active여도 매칭이 전혀 일어나지 않는다
                  // (matchesWatch가 hasWatchCriteria로 먼저 거른다). 목록에 그냥 떠 있으면
                  // 동작 중이라고 오해하게 되므로 여기서 명시적으로 알린다.
                  const usable = hasWatchCriteria(watch);
                  return (
                    <div key={watch.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <p className="text-sm font-medium">{watch.name}</p>
                            {watch.active ? (
                              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                                활성
                              </span>
                            ) : (
                              <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                                일시중지
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {describeWatchCriteria(watch).join(" · ") || "설정된 필터 없음"}
                          </p>
                          {!usable && (
                            <p className="mt-1.5 text-xs text-amber-700 dark:text-amber-400">
                              조건이 없어 알림이 발송되지 않습니다. 삭제 후 조건을 넣어 다시 만드세요.
                            </p>
                          )}
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1.5">
                          {usable && (
                            <form action={toggleWatchCondition}>
                              <input type="hidden" name="id" value={watch.id} />
                              <input type="hidden" name="nextActive" value={watch.active ? "false" : "true"} />
                              <button className="text-xs text-muted-foreground underline underline-offset-2">
                                {watch.active ? "일시중지" : "활성화"}
                              </button>
                            </form>
                          )}
                          <form action={deleteWatchCondition}>
                            <input type="hidden" name="id" value={watch.id} />
                            <button className="text-xs text-muted-foreground underline underline-offset-2">
                              Delete
                            </button>
                          </form>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
