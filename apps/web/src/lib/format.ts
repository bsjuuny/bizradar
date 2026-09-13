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

/**
 * Asia/Seoul 달력일 기준으로 마감일까지 남은 일수. 음수면 이미 지난 마감.
 * `formatDday`와 큐 정렬(`lib/queue.ts`)이 같은 계산을 공유하도록 분리했다.
 */
export function daysUntilDeadline(
  iso: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!iso) return null;
  const deadline = new Date(iso);
  if (Number.isNaN(deadline.getTime())) return null;
  const todayKey = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const deadlineKey = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(deadline);
  const day = 86_400_000;
  return Math.round(
    (Date.parse(`${deadlineKey}T00:00:00Z`) - Date.parse(`${todayKey}T00:00:00Z`)) / day,
  );
}

export function formatDday(
  iso: string | null | undefined,
  now: Date = new Date(),
): string {
  const diff = daysUntilDeadline(iso, now);
  if (diff === null) return "일정 미정";
  if (diff < 0) return "마감";
  if (diff === 0) return "D-Day";
  return `D-${diff}`;
}
