-- Phase 3: full text search over opportunities (title + organization).
--
-- Uses the 'simple' text search config, not 'english'/'korean': Postgres ships no
-- Korean dictionary, so 'simple' (whitespace/punctuation tokenization, no stemming) is
-- the honest choice here - it matches whole tokens, not substrings within a compound
-- Korean word. Good enough for MVP; a Korean-aware extension is a deliberate future
-- upgrade, not an oversight (see docs/DATABASE.md).

alter table opportunities
  add column search_vector tsvector
  generated always as (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(organization, '')), 'B')
  ) stored;

create index opportunities_search_idx on opportunities using gin (search_vector);
