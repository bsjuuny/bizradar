import Link from "next/link";
import { notFound } from "next/navigation";
import { getSupportProgram } from "@/lib/supportPrograms";
import { safeExternalUrl } from "@/lib/external-url";
import { formatDate } from "@/lib/format";
import { formatSupportDeadline, supportSourceLabel } from "@/lib/support-display";
import { InvestmentBadge } from "../investment-badge";

export default async function SupportProgramDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const program = await getSupportProgram(id);
  if (!program) notFound();
  // 기업마당 행의 department에는 담당부서가 아니라 소관기관(부처·광역지자체)이 들어 있다.
  const isBizinfo = program.source === "bizinfo";
  const sourceUrl = safeExternalUrl(program.source_url);

  return (
    <div className="flex flex-col gap-6">
      <Link href="/support" className="text-sm text-muted-foreground hover:underline">
        ← Support Radar 목록으로
      </Link>

      <header className="flex flex-col gap-3 border-b border-border pb-6">
        <div className="flex flex-wrap items-center gap-2">
          <InvestmentBadge linked={program.investment_linked} />
          {program.category && (
            <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs">
              {program.category}
            </span>
          )}
          <span className="text-xs font-medium tabular-nums text-muted-foreground">
            {formatSupportDeadline(
              program.application_end,
              program.application_period_text,
              program.is_open,
            )}
          </span>
          <span className="text-xs text-muted-foreground">
            {supportSourceLabel(program.source)}
            {program.it_related && " · IT 관련"}
          </span>
        </div>
        <h1 className="max-w-4xl text-2xl font-semibold text-balance">{program.title}</h1>
        <p className="text-sm text-muted-foreground">{program.organization ?? "주관기관 미확인"}</p>
      </header>

      <dl className="grid grid-cols-1 gap-x-8 gap-y-3 rounded-lg border border-border p-5 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">주관기관</dt>
          <dd>{program.organization ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{isBizinfo ? "소관기관" : "담당부서"}</dt>
          <dd>{program.department ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">주관유형</dt>
          <dd>{program.supervising_type ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">지역</dt>
          <dd>{program.region ?? (isBizinfo ? "—" : "제한 없음")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">신청대상</dt>
          <dd>{program.target ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">모집상태</dt>
          {/* is_open, not the raw flag: K-Startup's 모집 flag can still say Y after the
              deadline, and this must agree with the list and the 마감 badge above. */}
          <dd>{program.is_open ? "모집중" : "마감"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">접수시작</dt>
          <dd>{formatDate(program.application_start)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">접수마감</dt>
          <dd>{formatDate(program.application_end)}</dd>
        </div>
        {program.application_period_text && (
          <div className="sm:col-span-2">
            <dt className="text-muted-foreground">신청기간 (원문)</dt>
            <dd>{program.application_period_text}</dd>
          </div>
        )}
      </dl>

      {program.description && (
        <section className="rounded-lg border border-border p-5">
          <h2 className="text-sm font-semibold">사업 개요</h2>
          <p className="mt-3 text-sm whitespace-pre-line text-muted-foreground">
            {program.description}
          </p>
        </section>
      )}

      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="w-fit rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted"
        >
          {supportSourceLabel(program.source)} 원문 보기 ↗
        </a>
      )}
    </div>
  );
}
