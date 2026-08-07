import Link from "next/link";
import { requireCompany } from "@/lib/dal";
import { NavLinks } from "./nav-links";
import { logout } from "./actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { company } = await requireCompany();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 overflow-x-auto px-4 py-3">
          <div className="flex shrink-0 items-center gap-6">
            <Link href="/dashboard" className="text-lg font-semibold tracking-tight whitespace-nowrap">
              BizRadar
            </Link>
            <NavLinks />
          </div>
          <div className="flex shrink-0 items-center gap-3 text-sm whitespace-nowrap">
            <span className="text-muted-foreground">{company.name}</span>
            <form action={logout}>
              <button type="submit" className="underline">
                로그아웃
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
    </div>
  );
}
