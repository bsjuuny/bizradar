-- Postgres views freeze their column list at creation time - opportunities_current's
-- `select o.*` was resolved against the opportunities schema as it existed when the
-- view was created, so it never picked up industry_limited/participation_limited/
-- procurement_category added afterward (20260809010000). Found live: the new Market
-- Radar page errored with "column opportunities_current.industry_limited does not
-- exist". CREATE OR REPLACE re-resolves `o.*` against the current table schema - no
-- functional change to the view's filtering logic, same query text as
-- 20260809000000_notice_thread_dedup.sql.

create or replace view opportunities_current
  with (security_invoker = true)
  as
  select o.*
  from opportunities o
  where o.bid_ntce_no is null
  union all
  select o.*
  from opportunities o
  join (
    select bid_ntce_no, max(bid_ntce_ord) as latest_ord
    from opportunities
    where bid_ntce_no is not null
    group by bid_ntce_no
  ) latest
    on o.bid_ntce_no = latest.bid_ntce_no
   and o.bid_ntce_ord = latest.latest_ord
  where o.ntce_kind_nm is distinct from '취소공고';
