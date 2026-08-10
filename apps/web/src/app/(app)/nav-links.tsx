"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ALL_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/opportunities", label: "Project", hiddenWhilePending: true },
  { href: "/support", label: "Support", hiddenWhilePending: true },
  {
    href: "/challenges",
    label: "CHALLENGE",
    featureFlag: "challenge" as const,
    hiddenWhilePending: true,
  },
  { href: "/market", label: "시장 통계", adminOnly: true },
  { href: "/settings", label: "설정" },
  { href: "/admin", label: "회원 승인", adminOnly: true },
];

export function NavLinks({
  challengeEnabled,
  isAdmin,
  approved,
}: {
  challengeEnabled: boolean;
  isAdmin: boolean;
  approved: boolean;
}) {
  const pathname = usePathname();
  const links = ALL_LINKS.filter((link) => {
    if (link.adminOnly && !isAdmin) return false;
    if (link.featureFlag === "challenge" && !challengeEnabled) return false;
    // Hidden, not just gated server-side (apps/web/src/proxy.ts) - avoids dead-end
    // clicks for a company still waiting on approval. Admins bypass the proxy gate
    // entirely (see proxy.ts), so the nav must match or an admin would see a link
    // missing that actually still works.
    if (link.hiddenWhilePending && !approved && !isAdmin) return false;
    return true;
  });

  return (
    <nav className="flex w-max items-center gap-1">
      {links.map(({ href, label }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={
              "rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors " +
              (active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground")
            }
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
