import { describe, expect, it } from "vitest";
import { explainMatchBreakdown } from "./match-explanation";
import type { MatchScoreBreakdown } from "./opportunities";

function breakdown(overrides: Partial<MatchScoreBreakdown> = {}): MatchScoreBreakdown {
  return {
    technology_score: 30,
    business_type_score: 20,
    budget_score: 15,
    experience_score: 15,
    qualification_score: 10,
    region_score: 5,
    schedule_score: 5,
    total_score: 100,
    ...overrides,
  };
}

describe("explainMatchBreakdown", () => {
  it("marks a full-score category as 'full' with a positive message", () => {
    const [tech] = explainMatchBreakdown(breakdown());
    expect(tech.verdict).toBe("full");
    expect(tech.message).toContain("모두 보유");
  });

  it("marks a zero-score category as 'none' with a negative message", () => {
    const items = explainMatchBreakdown(breakdown({ budget_score: 0 }));
    const budget = items.find((i) => i.key === "budget_score")!;
    expect(budget.verdict).toBe("none");
    expect(budget.message).toContain("벗어납니다");
  });

  it("distinguishes 'opportunity has no stated budget' from 'company set no preference' for a full budget score", () => {
    const withBudget = explainMatchBreakdown(breakdown(), { budgetAmount: 500_000_000 });
    const budgetWithAmount = withBudget.find((i) => i.key === "budget_score")!;
    expect(budgetWithAmount.message).toContain("범위 안");

    const withoutBudget = explainMatchBreakdown(breakdown(), { budgetAmount: null });
    const budgetWithoutAmount = withoutBudget.find((i) => i.key === "budget_score")!;
    expect(budgetWithoutAmount.message).toContain("예산 정보가 없어");
  });

  it("marks a partial technology score as 'partial'", () => {
    const items = explainMatchBreakdown(breakdown({ technology_score: 15 }));
    const tech = items.find((i) => i.key === "technology_score")!;
    expect(tech.verdict).toBe("partial");
    expect(tech.message).toContain("일부");
  });

  it("uses the real deadline to phrase the schedule message", () => {
    const future = new Date(Date.now() + 10 * 86_400_000).toISOString();
    const items = explainMatchBreakdown(breakdown({ schedule_score: 5 }), { bidCloseAt: future });
    const schedule = items.find((i) => i.key === "schedule_score")!;
    expect(schedule.verdict).toBe("full");
    expect(schedule.message).toContain("여유");
  });

  it("gives a non-committal message for a zero schedule score (formatDday can't tell 'already past' from 'due today')", () => {
    const past = new Date(Date.now() - 86_400_000).toISOString();
    const items = explainMatchBreakdown(breakdown({ schedule_score: 0 }), { bidCloseAt: past });
    const schedule = items.find((i) => i.key === "schedule_score")!;
    expect(schedule.verdict).toBe("none");
    expect(schedule.message).toContain("임박했거나 이미 지났습니다");
  });

  it("distinguishes 'no deadline stated' (still full marks) from 'deadline is 7+ days away'", () => {
    const items = explainMatchBreakdown(breakdown({ schedule_score: 5 }), { bidCloseAt: null });
    const schedule = items.find((i) => i.key === "schedule_score")!;
    expect(schedule.verdict).toBe("full");
    expect(schedule.message).toContain("마감일 정보가 없어");
    expect(schedule.message).not.toContain("여유");
  });

  it("returns exactly the 7 scoring categories in a stable order", () => {
    const items = explainMatchBreakdown(breakdown());
    expect(items.map((i) => i.key)).toEqual([
      "technology_score",
      "business_type_score",
      "budget_score",
      "experience_score",
      "qualification_score",
      "region_score",
      "schedule_score",
    ]);
  });
});
