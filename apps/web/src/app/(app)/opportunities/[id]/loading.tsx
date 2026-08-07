export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      <div className="h-7 w-2/3 animate-pulse rounded bg-muted" />
      <div className="h-48 w-full animate-pulse rounded-lg bg-muted" />
    </div>
  );
}
