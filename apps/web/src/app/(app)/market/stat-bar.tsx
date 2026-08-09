const BAR_TONES = {
  neutral: "bg-foreground/70",
  primary: "bg-primary",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
} as const;

export function StatBar({
  label,
  count,
  total,
  tone = "neutral",
}: {
  label: string;
  count: number;
  total: number;
  tone?: keyof typeof BAR_TONES;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate">{label}</span>
        <span className="shrink-0 tabular-nums text-muted-foreground">
          {count.toLocaleString("ko-KR")}건 ({pct}%)
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${BAR_TONES[tone]}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
