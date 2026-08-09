import Link from "next/link";
import { notFound } from "next/navigation";
import { getSupportProgram } from "@/lib/supportPrograms";
import { formatDate, formatDday } from "@/lib/format";
import { InvestmentBadge } from "../investment-badge";

export default async function SupportProgramDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const program = await getSupportProgram(id);
  if (!program) notFound();

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
            {formatDday(program.application_end)}
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
          <dt className="text-muted-foreground">담당부서</dt>
          <dd>{program.department ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">주관유형</dt>
          <dd>{program.supervising_type ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">지역</dt>
          <dd>{program.region ?? "제한 없음"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">신청대상</dt>
          <dd>{program.target ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">모집상태</dt>
          <dd>{program.recruiting === null ? "—" : program.recruiting ? "모집중" : "마감"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">접수시작</dt>
          <dd>{formatDate(program.application_start)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">접수마감</dt>
          <dd>{formatDate(program.application_end)}</dd>
        </div>
      </dl>

      {program.description && (
        <section className="rounded-lg border border-border p-5">
          <h2 className="text-sm font-semibold">사업 개요</h2>
          <p className="mt-3 text-sm whitespace-pre-line text-muted-foreground">
            {program.description}
          </p>
        </section>
      )}

      {program.source_url && (
        <a
          href={program.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="w-fit rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted"
        >
          K-Startup 원문 보기 ↗
        </a>
      )}
    </div>
  );
}
