export function isChallengeEnabled(): boolean {
  return process.env.FEATURE_CHALLENGE !== "false";
}

// Market Radar (/market) is BizRadar-operator-only for now, not a per-company
// permission - there's no company-level "admin" role yet (company_members.role is only
// 'owner'/'member', and there's no invite flow that would ever create a 'member' row -
// see docs/DATABASE.md). ADMIN_EMAILS is server-only (never NEXT_PUBLIC_*) so the
// allowlist itself is never sent to the browser. A static env-var allowlist, not a DB
// table, matches this app's existing FEATURE_CHALLENGE pattern - appropriate for a
// small, rarely-changing set of operator accounts; revisit if this ever needs to be
// self-service or grow beyond a handful of people.
export function isPlatformAdmin(email: string | null | undefined): boolean {
  if (!email) return false;
  const allowlist = (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  return allowlist.includes(email.toLowerCase());
}

