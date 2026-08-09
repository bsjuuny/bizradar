import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { isPlatformAdmin } from "@/lib/features";

const PUBLIC_ROUTES = ["/", "/login", "/signup", "/privacy"];

// Reachable regardless of a company's approval_status - a PENDING company must still be
// able to see its own dashboard, edit its profile, and (mid-onboarding, before it even
// has a company row) reach /onboarding. See docs/PRIVACY.md's admin-approval feature.
const ALLOWED_WHILE_PENDING = ["/dashboard", "/settings", "/onboarding"];

// Optimistic auth check only - refreshes the Supabase session cookie and redirects
// unauthenticated users away from protected routes. RLS (see supabase/migrations) is
// the real security boundary; this just avoids an extra client-side redirect flash.
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  const isPublicRoute = PUBLIC_ROUTES.includes(path);

  if (!user && !isPublicRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  if (user && (path === "/login" || path === "/signup")) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  const isAllowedWhilePending = ALLOWED_WHILE_PENDING.some(
    (p) => path === p || path.startsWith(`${p}/`),
  );

  // BizRadar operators (apps/web/src/lib/features.ts:isPlatformAdmin) bypass this
  // entirely - an admin must never be locked out of the app by their own company's
  // approval state (a rare edge case, but a confusing one to debug if it happened).
  if (user && !isPublicRoute && !isAllowedWhilePending && !isPlatformAdmin(user.email)) {
    const { data: membership } = await supabase
      .from("company_members")
      .select("company:companies(approval_status)")
      .eq("user_id", user.id)
      .maybeSingle();

    // PostgREST types a to-one embed as an array in the generic case even though
    // company_members -> companies is a real many-to-one relationship - same gotcha
    // documented in apps/web/src/lib/opportunities.ts. No membership row at all (user
    // hasn't finished onboarding) is not this gate's concern - requireCompany() in
    // apps/web/src/lib/dal.ts handles that redirect once the page itself renders.
    const companyField = membership?.company as
      | { approval_status: string }
      | { approval_status: string }[]
      | undefined;
    const approvalStatus = Array.isArray(companyField)
      ? companyField[0]?.approval_status
      : companyField?.approval_status;

    if (approvalStatus && approvalStatus !== "APPROVED") {
      const url = request.nextUrl.clone();
      url.pathname = "/dashboard";
      return NextResponse.redirect(url);
    }
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/health|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
