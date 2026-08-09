import { requireAdmin } from "@/lib/dal";
import { createAdminClient } from "@/lib/supabase/admin";
import { formatDateTime } from "@/lib/format";
import { approveCompany, rejectCompany, revokeApproval } from "./actions";

const STATUS_LABELS: Record<string, string> = {
  PENDING: "승인 대기",
  APPROVED: "승인됨",
  REJECTED: "거절됨",
};

const STATUS_TONES: Record<string, string> = {
  PENDING: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  APPROVED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  REJECTED: "bg-muted text-muted-foreground",
};

export default async function AdminPage() {
  // Operator-only, same as /market - see apps/web/src/lib/features.ts:isPlatformAdmin.
  await requireAdmin();

  // Uses the admin (service_role) client, not the normal RLS-scoped client - an admin
  // must see every company to approve them, not just their own (RLS would otherwise
  // restrict this to the admin's own company like any other user).
  const admin = createAdminClient();

  const { data: companies, error } = await admin
    .from("companies")
    .select("id, name, size_band, industry, region, approval_status, created_at")
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(`회사 목록을 불러오지 못했습니다: ${error.message}`);
  }

  const companyIds = (companies ?? []).map((c) => c.id);
  const { data: members } =
    companyIds.length > 0
      ? await admin
          .from("company_members")
          .select("company_id, user_id")
          .in("company_id", companyIds)
      : { data: [] };

  const {
    data: { users },
  } = await admin.auth.admin.listUsers({ perPage: 1000 });
  const emailByUserId = new Map(users.map((u) => [u.id, u.email]));
  const ownerEmailByCompanyId = new Map(
    (members ?? []).map((m) => [m.company_id, emailByUserId.get(m.user_id) ?? "—"]),
  );

  const pending = (companies ?? []).filter((c) => c.approval_status === "PENDING");
  const others = (companies ?? []).filter((c) => c.approval_status !== "PENDING");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">회원 승인 관리</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          신규 가입 회사는 승인 전까지 대시보드・설정만 이용할 수 있습니다.
        </p>
      </div>

      <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
        <h2 className="text-sm font-semibold">
          승인 대기 중{" "}
          <span className="tabular-nums text-muted-foreground">({pending.length})</span>
        </h2>
        {pending.length === 0 ? (
          <p className="text-sm text-muted-foreground">승인 대기 중인 회사가 없습니다.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="px-3 py-2 font-medium">회사명</th>
                  <th className="px-3 py-2 font-medium">가입 이메일</th>
                  <th className="px-3 py-2 font-medium">규모/업종</th>
                  <th className="px-3 py-2 font-medium">가입일</th>
                  <th className="px-3 py-2 font-medium">처리</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((c) => (
                  <tr key={c.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 font-medium">{c.name}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {ownerEmailByCompanyId.get(c.id) ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {c.size_band} · {c.industry ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">
                      {formatDateTime(c.created_at)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-2">
                        <form action={approveCompany.bind(null, c.id)}>
                          <button
                            type="submit"
                            className="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/85"
                          >
                            승인
                          </button>
                        </form>
                        <form action={rejectCompany.bind(null, c.id)}>
                          <button
                            type="submit"
                            className="rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                          >
                            거절
                          </button>
                        </form>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
        <h2 className="text-sm font-semibold">전체 회사</h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-3 py-2 font-medium">회사명</th>
                <th className="px-3 py-2 font-medium">가입 이메일</th>
                <th className="px-3 py-2 font-medium">상태</th>
                <th className="px-3 py-2 font-medium">처리</th>
              </tr>
            </thead>
            <tbody>
              {others.map((c) => (
                <tr key={c.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-medium">{c.name}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {ownerEmailByCompanyId.get(c.id) ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONES[c.approval_status]}`}
                    >
                      {STATUS_LABELS[c.approval_status] ?? c.approval_status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <form action={revokeApproval.bind(null, c.id)}>
                      <button
                        type="submit"
                        className="rounded-md border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                      >
                        대기 상태로 되돌리기
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
