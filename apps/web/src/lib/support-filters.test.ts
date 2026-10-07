import { describe, expect, it } from "vitest";
import { type CopyHidingOptions, copyHidingFilter } from "./support-filters";

const base: CopyHidingOptions = {
  status: "open",
  itOnly: false,
  investmentOnly: false,
  source: undefined,
  categories: undefined,
  term: undefined,
  today: "2026-10-07",
  closingLimit: "2026-10-14",
};

describe("copyHidingFilter", () => {
  it("hides a copy only while its original is open", () => {
    expect(copyHidingFilter(base)).toBe("duplicate_of.is.null,not.and(original_open.is.true)");
    expect(copyHidingFilter({ ...base, status: "all" })).toBe(
      "duplicate_of.is.null,not.and(original_open.is.true)",
    );
  });

  it("requires the original's deadline in the closing window too", () => {
    expect(copyHidingFilter({ ...base, status: "closing" })).toBe(
      "duplicate_of.is.null,not.and(original_open.is.true,original_end.gte.2026-10-07,original_end.lte.2026-10-14)",
    );
  });

  it("applies every other active filter to the original as well", () => {
    expect(
      copyHidingFilter({
        ...base,
        itOnly: true,
        investmentOnly: true,
        categories: ["기술", "기술개발(R&D)"],
        term: "창업, 벤처",
      }),
    ).toBe(
      "duplicate_of.is.null,not.and(original_open.is.true,original_it_related.is.true," +
        'original_investment_linked.is.true,original_category.in.("기술","기술개발(R&D)"),' +
        'or(original_title.ilike."%창업, 벤처%",original_organization.ilike."%창업, 벤처%"))',
    );
  });

  it("never hides with a source filter - original and copy are never both listed", () => {
    expect(copyHidingFilter({ ...base, source: "bizinfo" })).toBeNull();
    expect(copyHidingFilter({ ...base, source: "kstartup" })).toBeNull();
  });
});
