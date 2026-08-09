import "server-only";

import { createClient as createSupabaseClient } from "@supabase/supabase-js";

// service_role bypasses RLS and column-level grants entirely - the one deliberate,
// narrowly-scoped exception to "the web app never holds SUPABASE_SERVICE_ROLE_KEY"
// (docs/ARCHITECTURE.md anticipated this: "unless a specific feature later requires
// it"). Company approval is that feature: `authenticated` has no UPDATE privilege on
// companies.approval_status at all (see the 20260809* migrations, and the live attack
// test documented there) precisely so no client-side path can self-approve - which
// means the *only* way to legitimately flip it is through server_role, gated by
// requireAdmin() before this is ever called. Never import this from a "use client"
// file or a route that isn't already behind requireAdmin().
export function createAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !serviceRoleKey) {
    throw new Error("SUPABASE_SERVICE_ROLE_KEY is not configured for the web app");
  }
  return createSupabaseClient(url, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}
