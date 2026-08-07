import type { Category } from "@/lib/opportunities";

const LABELS: Record<Category, string> = {
  LIKELY_IT: "IT 관련",
  NON_IT: "IT 무관",
  UNKNOWN: "미분류",
};

const STYLES: Record<Category, string> = {
  LIKELY_IT: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  NON_IT: "bg-muted text-muted-foreground",
  UNKNOWN: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

export function CategoryBadge({ category }: { category: Category }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${STYLES[category]}`}
    >
      {LABELS[category]}
    </span>
  );
}
