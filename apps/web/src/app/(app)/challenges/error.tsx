"use client";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-6"><p className="font-medium text-destructive">CHALLENGE 데이터를 불러오지 못했습니다.</p><p className="mt-1 text-sm text-muted-foreground">잠시 후 다시 시도해 주세요.</p><button type="button" onClick={reset} className="mt-4 rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted">다시 시도</button></div>;
}

