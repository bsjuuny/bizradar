"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { createCompany } from "./actions";

const SIZE_BANDS = ["1-5", "6-10", "11-20", "21-50", "51+"] as const;

export function OnboardingForm() {
  const [state, formAction, pending] = useActionState(createCompany, undefined);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="name" className="text-sm font-medium">
          회사명
        </label>
        <input
          id="name"
          name="name"
          required
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="size_band" className="text-sm font-medium">
          직원 규모
        </label>
        <select
          id="size_band"
          name="size_band"
          required
          defaultValue=""
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="" disabled>
            선택해주세요
          </option>
          {SIZE_BANDS.map((band) => (
            <option key={band} value={band}>
              {band}명
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="industry" className="text-sm font-medium">
          업종
        </label>
        <input
          id="industry"
          name="industry"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="region" className="text-sm font-medium">
          지역
        </label>
        <input
          id="region"
          name="region"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="business_type" className="text-sm font-medium">
          사업 형태
        </label>
        <input
          id="business_type"
          name="business_type"
          placeholder="예: SI, 웹에이전시, AI 개발사"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="founded_year" className="text-sm font-medium">
          설립연도
        </label>
        <input
          id="founded_year"
          name="founded_year"
          type="number"
          min={1900}
          max={2100}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        />
      </div>
      {state?.error && <p className="text-sm text-destructive">{state.error}</p>}
      <Button type="submit" disabled={pending}>
        {pending ? "생성 중..." : "시작하기"}
      </Button>
    </form>
  );
}
