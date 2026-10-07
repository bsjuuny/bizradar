import { ilikeAnyFilter, quotePostgrestValue } from "@/lib/postgrest";
import type { SupportSource, SupportStatus } from "@/lib/support-display";

export type CopyHidingOptions = {
  status: SupportStatus;
  itOnly: boolean;
  investmentOnly: boolean;
  source: SupportSource | undefined;
  /** Raw category values of the selected 지원분야 group, if any. */
  categories: readonly string[] | undefined;
  /** Trimmed search term, if any. */
  term: string | undefined;
  /** Seoul today and the end of the "7일 안에 마감" window, as YYYY-MM-DD. */
  today: string;
  closingLimit: string;
};

/**
 * The `.or()` filter that hides a 기업마당 copy (a support_programs_listing row with
 * duplicate_of) exactly when its K-Startup original is in the same result - i.e. the
 * original is open now and passes every other active filter too. Hiding a copy whose
 * original isn't listed would drop the program; this evaluates the same predicates on the
 * original's columns (original_*) instead of special-casing which views may hide.
 *
 * Returns null when no copy can be hidden: with a source filter the original (K-Startup)
 * and the copy (기업마당) are never in the same result.
 */
export function copyHidingFilter(options: CopyHidingOptions): string | null {
  if (options.source) return null;

  // A closed original never hides its copy, in any view - not even "마감 포함 전체": the
  // open 기업마당 copy is then the row that says the program can still be applied for.
  const originalListed = ["original_open.is.true"];
  if (options.status === "closing") {
    originalListed.push(
      `original_end.gte.${options.today}`,
      `original_end.lte.${options.closingLimit}`,
    );
  }
  if (options.itOnly) originalListed.push("original_it_related.is.true");
  if (options.investmentOnly) originalListed.push("original_investment_linked.is.true");
  if (options.categories) {
    const values = options.categories.map(quotePostgrestValue).join(",");
    originalListed.push(`original_category.in.(${values})`);
  }
  if (options.term) {
    originalListed.push(
      `or(${ilikeAnyFilter(["original_title", "original_organization"], options.term)})`,
    );
  }
  return `duplicate_of.is.null,not.and(${originalListed.join(",")})`;
}
