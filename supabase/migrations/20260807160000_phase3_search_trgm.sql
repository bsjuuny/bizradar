-- The tsvector/GIN full text search added in 20260807150000 only matches whole tokens
-- ('simple' config has no Korean stemmer), so searching "교육" finds nothing against a
-- title containing the compound token "교육여행" - a real UX problem, not a theoretical
-- one (verified against live data). pg_trgm gives efficient substring matching via
-- ILIKE, which is what Korean search actually needs here. Kept alongside the tsvector
-- column rather than replacing it - exact-token search (e.g. by organization name) is
-- still useful and the column does no harm.

create extension if not exists pg_trgm;

create index opportunities_title_trgm_idx on opportunities using gin (title gin_trgm_ops);
create index opportunities_organization_trgm_idx
  on opportunities using gin (organization gin_trgm_ops);
