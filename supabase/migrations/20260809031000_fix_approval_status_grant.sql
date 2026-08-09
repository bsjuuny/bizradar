-- The previous migration's `revoke update (approval_status) on companies from
-- authenticated` did NOT actually work - verified live with a real attack attempt
-- (sign up a throwaway user, PATCH their own company's approval_status via the anon key
-- + their session token): the update succeeded (200, row actually changed) despite the
-- revoke. Root cause, confirmed via `supabase db query` against
-- information_schema.column_privileges: the *table-wide*
-- `grant update on companies to authenticated` (20260807130000_phase1_grants.sql)
-- already grants UPDATE on every column including future ones. A column-specific
-- REVOKE only removes an explicit column-level grant entry - it does not touch a
-- broader table-level grant that already permits it, so there was nothing for the
-- revoke to actually remove.
--
-- Fix: revoke the table-wide UPDATE grant entirely and re-grant it only on the columns
-- the settings form actually needs to write - approval_status (and id/timestamps) are
-- deliberately excluded. Re-verified live after this migration: the same attack now
-- returns a 403, and a normal settings save still succeeds.
revoke update on companies from authenticated;

grant update (
  name, size_band, industry, region, business_type, founded_year,
  budget_min, budget_max, experience_years, qualifications
) on companies to authenticated;
