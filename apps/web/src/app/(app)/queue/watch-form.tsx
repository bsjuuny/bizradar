"use client";

import { useActionState } from "react";
import { createWatchCondition } from "./actions";

const inputClass = "rounded-md border border-border bg-background px-3 py-2 text-sm";

export function WatchForm() {
  const [state, formAction, pending] = useActionState(createWatchCondition, undefined);

  return (
    <form action={formAction} className="mt-4 flex flex-col gap-3">
      <input name="name" required placeholder="Rule name" className={inputClass} />
      <input name="keyword" placeholder="Keyword" className={inputClass} />
      <select name="category" className={inputClass} defaultValue="">
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
          className={`min-w-0 ${inputClass}`}
        />
        <input
          name="maxBudget"
          type="number"
          min="0"
          placeholder="Max budget"
          className={`min-w-0 ${inputClass}`}
        />
      </div>
      <input
        name="minMatchScore"
        type="number"
        min="0"
        max="100"
        placeholder="Min match score"
        className={inputClass}
      />
      <div aria-live="polite">
        {state?.error && <p className="text-xs text-destructive">{state.error}</p>}
        {state?.success && (
          <p className="text-xs text-emerald-600">Watch 조건을 만들었습니다.</p>
        )}
        {!state && (
          <p className="text-xs text-muted-foreground">
            키워드 · 카테고리 · 예산 · 최소 매칭점수 중{" "}
            <span className="font-medium">최소 하나</span>를 채워야 알림이 발송됩니다.
          </p>
        )}
      </div>
      <button
        disabled={pending}
        className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
      >
        {pending ? "만드는 중..." : "Create Watch"}
      </button>
    </form>
  );
}
