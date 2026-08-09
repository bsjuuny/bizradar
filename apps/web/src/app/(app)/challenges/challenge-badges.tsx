import type {
  ChallengeStatus,
  ChallengeType,
  ParticipationType,
  PolicyStatus,
} from "@/lib/challenges";

export const TYPE_LABELS: Record<ChallengeType, string> = {
  CONTEST: "공모전",
  HACKATHON: "해커톤",
  AI_COMPETITION: "AI 경진대회",
  DATA_COMPETITION: "데이터 경진대회",
  DEV_COMPETITION: "개발 경진대회",
  IDEA_COMPETITION: "아이디어 공모전",
  STARTUP_COMPETITION: "창업 경진대회",
  AWARD: "어워드",
  PUBLIC_DATA_COMPETITION: "공공데이터 대회",
  OTHER: "기타",
};

export const STATUS_LABELS: Record<ChallengeStatus, string> = {
  UPCOMING: "접수 예정",
  OPEN: "접수 중",
  CLOSING_SOON: "마감 임박",
  CLOSED: "마감",
  UNKNOWN: "일정 미정",
};

export const POLICY_LABELS: Record<PolicyStatus, string> = {
  REQUIRED: "AI 사용 필수",
  ALLOWED: "AI 사용 가능",
  LIMITED: "AI 조건부",
  PROHIBITED: "AI 사용 금지",
  UNKNOWN: "AI 정책 미확인",
};

export const PARTICIPATION_LABELS: Record<ParticipationType, string> = {
  ONLINE: "온라인",
  OFFLINE: "오프라인",
  HYBRID: "온·오프라인 병행",
  UNKNOWN: "참여 방식 미확인",
};

const POLICY_STYLES: Record<PolicyStatus, string> = {
  REQUIRED: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
  ALLOWED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  LIMITED: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  PROHIBITED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  UNKNOWN: "bg-muted text-muted-foreground",
};

const STATUS_STYLES: Record<ChallengeStatus, string> = {
  UPCOMING: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  OPEN: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  CLOSING_SOON: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  CLOSED: "bg-muted text-muted-foreground",
  UNKNOWN: "bg-muted text-muted-foreground",
};

export function PolicyBadge({ policy }: { policy: PolicyStatus }) {
  return (
    <span className={`rounded-full px-2 py-1 text-xs font-medium ${POLICY_STYLES[policy]}`}>
      🤖 {POLICY_LABELS[policy]}
    </span>
  );
}

export function StatusBadge({ status }: { status: ChallengeStatus }) {
  return (
    <span className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

export function TypeBadge({ type }: { type: ChallengeType }) {
  return <span className="rounded-full bg-muted px-2 py-1 text-xs font-medium">{TYPE_LABELS[type]}</span>;
}
