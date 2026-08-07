const KRW_FORMATTER = new Intl.NumberFormat("ko-KR");

export function formatCurrencyKRW(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return `${KRW_FORMATTER.format(amount)}원`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  // hour12: false sidesteps a Node ICU gap where ko-KR's AM/PM day period falls back
  // to English ("PM") instead of 오전/오후 - 24-hour time is also just clearer here.
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
    hour12: false,
  }).format(date);
}
