import Link from "next/link";
import { requireCompany, requireUser } from "@/lib/dal";
import { NavLinks } from "./nav-links";
import { logout } from "./actions";
import { isChallengeEnabled, isPlatformAdmin } from "@/lib/features";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { company } = await requireCompany();
  const user = await requireUser(); // already resolved above via requireCompany - cached, no extra query

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-border/80 bg-background/95 backdrop-blur">
        <div className="mx-auto grid w-full max-w-7xl grid-cols-[1fr_auto] items-center gap-x-4 gap-y-3 px-4 py-3 sm:px-6 md:grid-cols-[auto_1fr_auto]">
          <Link href="/dashboard" className="text-lg font-semibold tracking-tight whitespace-nowrap">
            BizRadar
          </Link>
          <div className="order-3 col-span-2 min-w-0 overflow-x-auto md:order-none md:col-span-1 md:overflow-visible">
            <NavLinks
              challengeEnabled={isChallengeEnabled()}
              isAdmin={isPlatformAdmin(user.email)}
              approved={company.approval_status === "APPROVED"}
            />
          </div>
          <div className="flex min-w-0 items-center justify-end gap-3 text-sm whitespace-nowrap">
            <span className="max-w-32 truncate text-muted-foreground sm:max-w-48" title={company.name}>
              {company.name}
            </span>
            <form action={logout}>
              <button type="submit" className="rounded-md px-2 py-1 underline underline-offset-4 hover:bg-muted">
                로그아웃
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-10">{children}</main>
    </div>
  );
}
