"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm">
      <p className="font-medium text-destructive">공고 목록을 불러오지 못했습니다.</p>
      <p className="text-muted-foreground">{error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="rounded-lg border border-border px-3 py-1.5 hover:bg-muted"
      >
        다시 시도
      </button>
    </div>
  );
}
