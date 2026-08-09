export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-8 w-40 animate-pulse rounded bg-muted" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-40 w-full animate-pulse rounded-xl bg-muted" />
        <div className="h-40 w-full animate-pulse rounded-xl bg-muted" />
        <div className="h-40 w-full animate-pulse rounded-xl bg-muted" />
      </div>
      <div className="h-64 w-full animate-pulse rounded-xl bg-muted" />
    </div>
  );
}
