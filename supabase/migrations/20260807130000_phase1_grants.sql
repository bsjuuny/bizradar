-- RLS policies only *restrict* access an existing GRANT allows - they do not grant
-- access by themselves. Tables created via raw SQL (as opposed to the dashboard table
-- editor) don't get anon/authenticated privileges automatically, so grant exactly the
-- operations each Phase 1 RLS policy allows (see 20260807120000_phase1_company_profile.sql).

grant usage on schema public to anon, authenticated;

grant select on technologies to authenticated;

grant select, insert, update on companies to authenticated;

grant select, insert on company_members to authenticated;

grant select, insert, delete on company_technologies to authenticated;

grant select on worker_heartbeats to authenticated;
