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
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  }).format(date);
}
