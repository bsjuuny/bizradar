import Link from "next/link";
import { formatCurrencyKRW, formatDateTime, formatDday } from "@/lib/format";
import { getTodayQueue, type QueueItem, type QueueStatus } from "@/lib/queue";
import { MatchScoreBadge } from "../opportunities/match-score-badge";
import { createWatchCondition, deleteWatchCondition, removeSavedOpportunity, saveOpportunity } from "./actions";

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
  const highPriority = queue.items.filter((item) => item.saved || item.watchMatches.length > 0 || (item.matchScore ?? 0) >= 70);
  const visibleItems = highPriority.length > 0 ? highPriority : queue.items.slice(0, 20);

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

      <section className="grid gap-3 sm:grid-cols-3">
        {[
          ["Saved", queue.savedCount],
          ["Responding", queue.respondingCount],
          ["Watch rules", queue.watchConditions.length],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-3">
          {visibleItems.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
              No opportunities are ready for the queue yet.
            </div>
          ) : (
            visibleItems.map((item) => <QueueCard key={item.id} item={item} />)
          )}
        </div>

        <aside className="flex flex-col gap-4">
          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">New Watch Condition</h2>
            <form action={createWatchCondition} className="mt-4 flex flex-col gap-3">
              <input
                name="name"
                required
                placeholder="Rule name"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
              <input
                name="keyword"
                placeholder="Keyword"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
              <select name="category" className="rounded-md border border-border bg-background px-3 py-2 text-sm" defaultValue="">
                <option value="">Any category</option>
                <option value="LIKELY_IT">Likely IT</option>
                <option value="NON_IT">Non-IT</option>
                <option value="UNKNOWN">Unknown</option>
              </select>
              <div className="grid grid-cols-2 gap-2">
                <input
                  name="minBudget"
                  type="number"
                  min="0"
                  placeholder="Min budget"
                  className="min-w-0 rounded-md border border-border bg-background px-3 py-2 text-sm"
                />
                <input
                  name="maxBudget"
                  type="number"
                  min="0"
                  placeholder="Max budget"
                  className="min-w-0 rounded-md border border-border bg-background px-3 py-2 text-sm"
                />
              </div>
              <input
                name="minMatchScore"
                type="number"
                min="0"
                max="100"
                placeholder="Min match score"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
              <button className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
                Create Watch
              </button>
            </form>
          </section>

          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="text-sm font-semibold">Active Watches</h2>
            <div className="mt-3 flex flex-col gap-2">
              {queue.watchConditions.length === 0 ? (
                <p className="text-sm text-muted-foreground">No watch conditions yet.</p>
              ) : (
                queue.watchConditions.map((watch) => (
                  <div key={watch.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium">{watch.name}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {[
                            watch.keyword && `keyword: ${watch.keyword}`,
                            watch.category && `category: ${watch.category}`,
                            watch.min_match_score !== null && `score >= ${watch.min_match_score}`,
                          ].filter(Boolean).join(" · ") || "Any open opportunity"}
                        </p>
                      </div>
                      <form action={deleteWatchCondition}>
                        <input type="hidden" name="id" value={watch.id} />
                        <button className="text-xs text-muted-foreground underline underline-offset-2">
                          Delete
                        </button>
                      </form>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
