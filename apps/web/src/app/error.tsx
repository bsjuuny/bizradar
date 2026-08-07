"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-start justify-center gap-3 px-4 py-8 text-sm">
      <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-6">
        <p className="font-medium text-destructive">문제가 발생했습니다.</p>
        <p className="text-muted-foreground">{error.message}</p>
        <button
          type="button"
          onClick={reset}
          className="rounded-lg border border-border px-3 py-1.5 hover:bg-muted"
        >
          다시 시도
        </button>
      </div>
    </div>
  );
}
