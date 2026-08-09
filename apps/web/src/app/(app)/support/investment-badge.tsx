export function InvestmentBadge({ linked }: { linked: boolean }) {
  if (!linked) return null;
  return (
    <span className="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium whitespace-nowrap text-violet-800 dark:bg-violet-950 dark:text-violet-300">
      투자연계
    </span>
  );
}
