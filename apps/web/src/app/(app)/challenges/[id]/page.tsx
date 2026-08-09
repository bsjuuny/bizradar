import Link from "next/link";
import { notFound } from "next/navigation";
import { getChallenge, safeExternalUrl, type PolicyStatus } from "@/lib/challenges";
import { isChallengeEnabled } from "@/lib/features";
import { formatCurrencyKRW, formatDate, formatDday } from "@/lib/format";
import {
  PARTICIPATION_LABELS,
  POLICY_LABELS,
  PolicyBadge,
  StatusBadge,
  TypeBadge,
} from "../challenge-badges";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="min-w-0 rounded-lg bg-muted/50 p-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 whitespace-pre-wrap font-medium leading-6">{children || "미확인"}</dd></div>;
}

function PolicyRow({ label, value }: { label: string; value: PolicyStatus }) {
  return <div className="flex items-center justify-between gap-4 border-b border-border py-3 last:border-0"><span>{label}</span><span className="text-right text-sm font-medium">{POLICY_LABELS[value]}</span></div>;
}

export default async function ChallengeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  if (!isChallengeEnabled()) notFound();
  const { id } = await params;
  const challenge = await getChallenge(id);
  if (!challenge) notFound();
  const sourceUrl = safeExternalUrl(challenge.source_url);
  const applicationUrl = safeExternalUrl(challenge.application_url);
  const attachments = challenge.attachments
    .map((attachment) => ({ ...attachment, safeUrl: safeExternalUrl(attachment.url) }))
    .filter((attachment) => attachment.safeUrl);
  const tags = Array.from(new Set([...challenge.categories, ...challenge.technology_keywords]));

  return (
    <div className="flex flex-col gap-6">
      <Link href="/challenges" className="text-sm text-muted-foreground hover:underline">← CHALLENGE 목록으로</Link>
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2"><TypeBadge type={challenge.challenge_type} /><StatusBadge status={challenge.status} /><PolicyBadge policy={challenge.ai_policy} /></div>
        <h1 className="text-2xl font-semibold text-balance">{challenge.title}</h1>
        <p className="text-sm text-muted-foreground">{challenge.organizer ?? "주최기관 미확인"}</p>
      </header>

      <section className="rounded-xl border border-border p-5">
        <h2 className="font-semibold">기본정보</h2>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Field label="접수기간">{formatDate(challenge.apply_start_date)} ~ {formatDate(challenge.apply_end_date)} ({formatDday(challenge.apply_end_date)})</Field>
          <Field label="행사기간">{formatDate(challenge.start_date)} ~ {formatDate(challenge.end_date)}</Field>
          <Field label="결과 발표">{formatDate(challenge.result_date)}</Field>
          <Field label="참가자격">{challenge.eligibility}</Field>
          <Field label="팀 구성">{challenge.team_min || challenge.team_max ? `${challenge.team_min ?? 1}~${challenge.team_max ?? "미정"}명` : "미확인"}</Field>
          <Field label="참여 방식">{PARTICIPATION_LABELS[challenge.participation_type]}</Field>
          <Field label="지역">{challenge.region}</Field>
          <Field label="상금">{challenge.prize_description ?? challenge.prize ?? formatCurrencyKRW(challenge.total_prize_amount)}</Field>
          <Field label="주관/후원">{[challenge.host, challenge.sponsor].filter(Boolean).join(" / ")}</Field>
        </dl>
      </section>

      <section className="rounded-xl border border-border p-5">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">AI 활용 정책</h2><PolicyBadge policy={challenge.ai_policy} /></div>
        {challenge.ai_policy_evidence ? <blockquote className="mt-4 rounded-lg bg-muted p-4 text-sm"><p className="font-medium">판정 근거{challenge.ai_policy_source_section ? ` · ${challenge.ai_policy_source_section}` : ""}</p><p className="mt-2 text-muted-foreground">“{challenge.ai_policy_evidence}”</p></blockquote> : <p className="mt-4 rounded-lg bg-muted/60 p-4 text-sm text-muted-foreground">공고 원문에서 명확한 AI 활용 규정을 확인하지 못했습니다. 확인 전까지는 정책 미확인 상태로 안내합니다.</p>}
        {challenge.analysis_status === "FAILED" && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">AI 정책 분석이 일시 실패하여 보수적인 규칙 기반 결과를 표시합니다.</p>}
        <div className="mt-4 text-sm"><PolicyRow label="AI 코딩 도구" value={challenge.ai_coding_policy} /><PolicyRow label="대화형 AI" value={challenge.llm_policy} /><PolicyRow label="생성형 이미지" value={challenge.ai_image_policy} /><PolicyRow label="생성형 영상" value={challenge.ai_video_policy} /><PolicyRow label="생성형 음성" value={challenge.ai_audio_policy} /><PolicyRow label="외부 AI API" value={challenge.external_ai_api_policy} /></div>
      </section>

      <section className="rounded-xl border border-border p-5">
        <h2 className="font-semibold">제출·권리 정책</h2>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <Field label="필수 제출물">{challenge.required_documents.join("\n")}</Field>
          <Field label="제출 방법">{challenge.submission_requirements.join("\n")}</Field>
          <Field label="외부 API 정책">{challenge.external_api_policy}</Field>
          <Field label="오픈소스 정책">{challenge.open_source_policy}</Field>
          <Field label="저작권">{challenge.copyright_policy}</Field>
          <Field label="결과물 소유권">{challenge.ownership_policy}</Field>
        </dl>
      </section>

      {attachments.length > 0 && <section className="rounded-xl border border-border p-5"><h2 className="font-semibold">첨부파일</h2><ul className="mt-3 space-y-2 text-sm">{attachments.map((attachment) => <li key={`${attachment.name}-${attachment.safeUrl}`}><a href={attachment.safeUrl!} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4">{attachment.name} ↗</a>{attachment.media_type && <span className="ml-2 text-xs text-muted-foreground">{attachment.media_type}</span>}</li>)}</ul></section>}

      {tags.length > 0 && <section className="rounded-xl border border-border p-5"><h2 className="font-semibold">분야·기술</h2><div className="mt-3 flex flex-wrap gap-2">{tags.map((tag) => <span key={tag} className="rounded-full bg-muted px-2.5 py-1 text-xs">#{tag}</span>)}</div></section>}

      <details className="group rounded-xl border border-border bg-card p-5">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
          <span>공고 원문</span>
          <span className="text-xs font-normal text-muted-foreground group-open:hidden">펼쳐보기</span>
          <span className="hidden text-xs font-normal text-muted-foreground group-open:inline">접기</span>
        </summary>
        <p className="mt-4 max-h-[36rem] overflow-y-auto whitespace-pre-wrap border-t border-border pt-4 text-sm leading-7 text-muted-foreground">{challenge.original_text}</p>
      </details>

      <div className="flex flex-wrap gap-3">
        {sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">공고 원문 보기 ↗</a>}
        {applicationUrl && <a href={applicationUrl} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted">공식 신청 페이지 ↗</a>}
      </div>
    </div>
  );
}
