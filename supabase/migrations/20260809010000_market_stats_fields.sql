-- Normalized fields for Market Radar-style statistics on IT-classified opportunities
-- (입찰자격/투찰제한 breakdowns) - see docs/DATA_PIPELINE.md#market-statistics. Following
-- the same RAW -> NORMALIZED pattern as bid_ntce_no/etc: the web app queries these
-- columns, not raw_payload JSON paths, so it never has to know G2B's field naming.

alter table opportunities
  add column industry_limited boolean,
  add column participation_limited boolean,
  add column procurement_category text;

create index opportunities_procurement_category_idx on opportunities (procurement_category);
