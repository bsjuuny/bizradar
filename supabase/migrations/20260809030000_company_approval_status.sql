-- Sign-up approval gate: a newly onboarded company starts PENDING and can only reach
-- /dashboard and /settings until a BizRadar operator approves it (docs/PRIVACY.md's
-- admin concept - see apps/web/src/lib/features.ts:isPlatformAdmin). Default is
-- 'APPROVED', not 'PENDING' - existing companies created before this feature existed
-- must not be suddenly locked out. New companies get 'PENDING' explicitly at insert
-- time (apps/web/src/app/onboarding/actions.ts), not via this column default.

alter table companies
  add column approval_status text not null default 'APPROVED'
    check (approval_status in ('PENDING', 'APPROVED', 'REJECTED'));

-- companies_update_own's RLS policy only restricts which ROW a user can update
-- (id = auth_company_id()), not which COLUMNS - the table-wide
-- `grant update on companies to authenticated` (20260807130000_phase1_grants.sql) would
-- otherwise let any authenticated user self-approve with a raw PostgREST PATCH request
-- (`/rest/v1/companies?id=eq.<their-own-id>` with `{"approval_status":"APPROVED"}`),
-- completely bypassing this feature - found by checking the RLS policy before assuming
-- the UI/server-action code was the only way in. Only service_role (which bypasses
-- grants and RLS entirely) can change this column now.
revoke update (approval_status) on companies from authenticated;
