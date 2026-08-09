# Privacy & Personal Data

## Status: implemented 2026-08-09

BizRadar's actual personal-data surface is small: an email address and a hashed
password per user (`auth.users`, managed by Supabase Auth), plus company profile data
(name, industry, region, business type, etc.) that describes a *business*, not an
individual, and isn't treated as personal data here. There is no resident registration
number, no phone number, no physical address collection anywhere in this app.

## What's implemented

- **`/privacy`** (`apps/web/src/app/privacy/page.tsx`) - a real 개인정보처리방침 covering
  the PIPA-required sections: collected items, purpose, retention, processing
  outsourcing (Supabase), cross-border transfer, data subject rights, destruction
  procedure, technical safeguards, and a privacy officer contact section. Public route
  (`apps/web/src/proxy.ts`'s `PUBLIC_ROUTES`), reachable pre-login since `/signup` links
  to it before a session exists.
- **Signup consent** (`apps/web/src/app/signup/`) - a required "개인정보 수집 및 이용에
  동의합니다" checkbox linking to `/privacy`. Enforced server-side in `actions.ts` (not
  just the HTML `required` attribute, which a client could bypass), and recorded with a
  timestamp on the auth user itself via `supabase.auth.signUp()`'s
  `options.data.privacy_consent_at` - so consent has verifiable per-user evidence, not
  just a UI checkbox nobody can prove was checked.

## Technical safeguards (what's actually true, not aspirational)

- **Password storage**: never touches BizRadar's own code or database. `supabase.auth
  .signUp()`/`signInWithPassword()` delegate entirely to Supabase Auth, which hashes
  passwords server-side before storage - the app never sees or logs a raw password
  beyond passing it once, over HTTPS, to Supabase's auth endpoint.
- **Transport encryption**: all Supabase traffic (auth, database, storage) is HTTPS/TLS.
- **At-rest encryption**: handled at the Supabase/cloud-provider infrastructure level,
  not something this app's code implements separately.
- **Access control**: RLS scopes every company-relevant table to `auth_company_id()` -
  see `docs/DATABASE.md#rls`. `SUPABASE_SERVICE_ROLE_KEY` was worker-only until
  2026-08-09; the web app now also holds it, exclusively for admin-only actions
  (`apps/web/src/lib/supabase/admin.ts`) - see the sign-up approval section below and
  `docs/ARCHITECTURE.md`. Still never bundled into the client and never sent to the
  browser - verified via secret-scan before every commit
  (`docs/VERIFICATION_REPORT.md`).
- **Sign-up approval gate** (`companies.approval_status`, implemented 2026-08-09): a
  newly onboarded company can only reach `/dashboard` and `/settings`
  (`apps/web/src/proxy.ts`) until a BizRadar operator approves it at `/admin`. Live
  attack-tested, including one real vulnerability found and fixed this pass: a naive
  `REVOKE` on the approval column didn't actually work (see `docs/DATABASE.md`'s
  gotchas), and a self-approval PATCH succeeded before the fix - confirmed blocked
  (403) after it, with a normal settings save still working.
- **No email logging found**: checked before shipping this - no `console.log`/
  `console.error`/Python `logger.*` call anywhere in `apps/web/src` or `worker` logs a
  user's email address. Error logs use Postgres error objects (`error.message`), not
  user-identifying fields.

## Known gaps (not implemented, said plainly rather than hidden)

- **No self-service account deletion yet.** `/privacy` states this explicitly and
  directs deletion requests to a manual contact-based process instead of overstating a
  feature that doesn't exist. A real "탈퇴" flow (delete `auth.users` + cascade
  `company_members`/`companies` the user solely owns) is future work.
- **Privacy officer contact info is a placeholder** (`[담당자명]`, `[연락처 이메일]`) -
  this is real business/legal information only the company itself can supply; it must
  be filled in with a real name and contact before this goes to production users.
- **Cross-border transfer section is generic** pending a confirmed Supabase project
  region - the specific country/region needs to be named once that's locked in.
- **No formal data retention automation** - retention is currently "until account
  deletion is requested," which is honestly what's true today, not "N days then
  auto-purged." Building actual scheduled purging is future work if/when it's needed.
