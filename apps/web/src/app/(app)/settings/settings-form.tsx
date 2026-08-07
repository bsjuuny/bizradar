"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import type { CompanyMembership } from "@/lib/dal";
import type { Technology } from "@/lib/settings";
import { updateSettings } from "./actions";

const SIZE_BANDS = ["1-5", "6-10", "11-20", "21-50", "51+"] as const;

const inputClass = "rounded-lg border border-border bg-background px-3 py-2 text-sm";

export function SettingsForm({
  company,
  technologies,
  selectedTechnologyIds,
}: {
  company: CompanyMembership["company"];
  technologies: Technology[];
  selectedTechnologyIds: Set<string>;
}) {
  const [state, formAction, pending] = useActionState(updateSettings, undefined);

  return (
    <form action={formAction} className="flex flex-col gap-8">
      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-muted-foreground">회사 정보</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="name" className="text-sm font-medium">
              회사명
            </label>
            <input id="name" name="name" defaultValue={company.name} required className={inputClass} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="size_band" className="text-sm font-medium">
              직원 규모
            </label>
            <select
              id="size_band"
              name="size_band"
              defaultValue={company.size_band}
              required
              className={inputClass}
            >
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
              defaultValue={company.industry ?? ""}
              className={inputClass}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="region" className="text-sm font-medium">
              지역
            </label>
            <input id="region" name="region" defaultValue={company.region ?? ""} className={inputClass} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="business_type" className="text-sm font-medium">
              사업 형태
            </label>
            <input
              id="business_type"
              name="business_type"
              placeholder="예: SI, 웹에이전시, AI 개발사"
              defaultValue={company.business_type ?? ""}
              className={inputClass}
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
              defaultValue={company.founded_year ?? ""}
              className={inputClass}
            />
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground">Company Match 프로필</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Project Radar의 매칭 점수 계산에 사용됩니다. 비워두면 해당 항목은 조건 없음으로
            처리됩니다.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <label htmlFor="budget_min" className="text-sm font-medium">
              희망 예산 (최소, 원)
            </label>
            <input
              id="budget_min"
              name="budget_min"
              type="number"
              min={0}
              defaultValue={company.budget_min ?? ""}
              className={inputClass}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="budget_max" className="text-sm font-medium">
              희망 예산 (최대, 원)
            </label>
            <input
              id="budget_max"
              name="budget_max"
              type="number"
              min={0}
              defaultValue={company.budget_max ?? ""}
              className={inputClass}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="experience_years" className="text-sm font-medium">
              경력 연수
            </label>
            <input
              id="experience_years"
              name="experience_years"
              type="number"
              min={0}
              defaultValue={company.experience_years}
              className={inputClass}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="qualifications" className="text-sm font-medium">
              보유 자격/인증 (쉼표로 구분)
            </label>
            <input
              id="qualifications"
              name="qualifications"
              placeholder="예: SW사업자 등록, 정보보호관리체계 인증"
              defaultValue={company.qualifications.join(", ")}
              className={inputClass}
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">기술 스택</span>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border border-border p-4 sm:grid-cols-3 md:grid-cols-4">
            {technologies.map((tech) => (
              <label key={tech.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="technology_ids"
                  value={tech.id}
                  defaultChecked={selectedTechnologyIds.has(tech.id)}
                  className="rounded border-border"
                />
                {tech.name}
              </label>
            ))}
          </div>
        </div>
      </section>

      {state?.error && <p className="text-sm text-destructive">{state.error}</p>}
      {state?.success && <p className="text-sm text-emerald-600">저장되었습니다.</p>}

      <Button type="submit" disabled={pending} className="w-fit">
        {pending ? "저장 중..." : "저장"}
      </Button>
    </form>
  );
}
